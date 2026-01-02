import tweepy
import os
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Any
from typing import cast
from tweepy.client import Response

def _get_bearer_token_from_env(var_name: str = "BEARER_TOKEN") -> str:
    token = os.environ.get(var_name)
    if token is None or not token.strip():
        raise RuntimeError(
            f"Missing {var_name} environment variable. "
            "Set it to your X Developer Portal app 'Bearer Token' (no 'Bearer ' prefix)."
        )

    token = token.strip()
    if token.lower().startswith("bearer "):
        # Tweepy will add the 'Bearer ' prefix itself.
        token = token[7:].strip()

    return token

def _dt_utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _ensure_data_dir() -> Path:
    root = Path(__file__).resolve().parent
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def _best_effort_first_10_responses(
    client: tweepy.Client,
    tweet_id: str,
) -> tuple[list[dict[str, Any]], str | None]:
    """Best-effort: replies require Search access and are often limited to 'recent' window."""

    query = f"conversation_id:{tweet_id} is:reply"
    try:
        resp = client.search_recent_tweets(
            query=query,
            max_results=10,
            tweet_fields=["created_at", "public_metrics", "author_id"],
            expansions=["author_id"],
            user_fields=["username", "name"],
        )
    except Exception as exc:
        return ([], f"search_recent_tweets failed: {type(exc).__name__}: {exc}")

    resp = cast(Response, resp)
    users_by_id: dict[str, dict[str, Any]] = {}
    if getattr(resp, "includes", None) and resp.includes.get("users"):
        for u in resp.includes["users"]:
            users_by_id[str(u.id)] = {"id": str(u.id), "username": u.username, "name": u.name}

    out: list[dict[str, Any]] = []
    for t in (resp.data or []):
        author_id = str(getattr(t, "author_id", "")) if getattr(t, "author_id", None) else None
        out.append(
            {
                "id": str(t.id),
                "created_at": _iso(getattr(t, "created_at", None)),
                "text": t.text,
                "author": users_by_id.get(author_id) if author_id else None,
                "public_metrics": getattr(t, "public_metrics", None),
            }
        )

    return (out, None)


def run_tweepy_crawl(client: tweepy.Client, username: str) -> None:
    # Interpreting the requested range as Dec 1–5 of the current year (UTC).
    year = datetime.now(timezone.utc).year
    start_time = _dt_utc(year, 12, 1)
    # X API expects end_time to be exclusive; use Dec 6 00:00Z to include all of Dec 5.
    end_time = _dt_utc(year, 12, 6)

    user_resp = client.get_user(username=username)
    user_data: tweepy.User | None = user_resp.data # type: ignore
    if user_data is None:
        raise RuntimeError(f"User not found: {username}")

    user_id = str(user_data.id)
    # Note: X API v2 'views' are not part of public metrics. They may be available via
    # non_public_metrics/organic_metrics with higher access levels + user auth.
    notes: dict[str, Any] = {
        "range": {
            "start_time": _iso(start_time),
            "end_time_exclusive": _iso(end_time),
            "timezone": "UTC",
        },
        "views": "Not available via public_metrics with bearer-token app auth; saved as null.",
        "quotes": "Available via public_metrics as quote_count; saved as metrics.quotes.",
        "responses": "Best-effort via search_recent_tweets; may be unavailable outside recent window or without access.",
    }

    tweets: list[dict[str, Any]] = []
    paginator = tweepy.Paginator(
        client.get_users_tweets,
        id=user_id,
        start_time=start_time,
        end_time=end_time,
        exclude=["retweets", "replies"],
        max_results=100,
        tweet_fields=["created_at", "public_metrics", "conversation_id"],
    )

    for page in paginator:
        page = cast(Response, page)
        for t in (page.data or []):
            pm = getattr(t, "public_metrics", None) or {}
            # 'public_metrics' does not include view counts.
            tweet_item: dict[str, Any] = {
                "id": str(t.id),
                "created_at": _iso(getattr(t, "created_at", None)),
                "text": t.text,
                "metrics": {
                    "replies": pm.get("reply_count"),
                    "reposts": pm.get("retweet_count"),
                    "likes": pm.get("like_count"),
                    "quotes": pm.get("quote_count"),
                    "views": None,
                },
            }

            # Optional: first 10 responses (best-effort)
            responses, responses_error = _best_effort_first_10_responses(client, str(t.id))
            tweet_item["first_10_responses"] = responses
            if responses_error:
                tweet_item["first_10_responses_status"] = "unavailable"
                tweet_item["first_10_responses_error"] = responses_error
            elif len(responses) == 0:
                tweet_item["first_10_responses_status"] = "ok-empty"
                tweet_item[
                    "first_10_responses_note"
                ] = "0 replies returned; this can mean no replies, or that replies are not accessible via recent search on your plan/window."
            else:
                tweet_item["first_10_responses_status"] = "ok"

            tweets.append(tweet_item)

    # Oldest -> newest
    tweets.sort(key=lambda x: (x.get("created_at") or ""))

    payload: dict[str, Any] = {
        "username": username,
        "user_id": user_id,
        "generated_at": _iso(datetime.now(timezone.utc)),
        "notes": notes,
        "tweets": tweets,
    }

    data_dir = _ensure_data_dir()
    out_path = data_dir / f"{username}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] Saved {len(tweets)} tweets to {out_path}")


def main():
    bearer_token = _get_bearer_token_from_env("BEARER_TOKEN")
    client = tweepy.Client(bearer_token=bearer_token)

    try:
        user = client.get_user(username="aoc")
        print(user)
    except Exception as exc:
        raise RuntimeError(
            "401 Unauthorized from X API. Common causes:\n"
            "- BEARER_TOKEN is wrong/expired/revoked (regenerate it in the X Developer Portal)\n"
            "- You accidentally pasted the 'Bearer ' prefix into BEARER_TOKEN (remove it)\n"
            "- You're using credentials from a different Project/App environment than expected\n"
            "- Your X plan/app doesn't have access to the endpoint you're calling\n\n"
            "Quick checks (PowerShell):\n"
            "$env:BEARER_TOKEN.Length\n"
            "(should be > 0; do NOT print the token itself)"
        ) from exc
    
    usernames: list[str] = [
        "aoc",
        "realDonaldTrump"
    ]

    for username in usernames:
        run_tweepy_crawl(client, username)