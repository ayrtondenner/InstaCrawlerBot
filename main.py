import driver_service
import crawlers.twitter as twitter_crawler

if __name__ == "__main__":

    urls = [
        "https://x.com/aoc",
        "https://x.com/realDonaldTrump"
    ]

    for url in urls:
        print(f"URL: {url}")
        driver = driver_service.get_driver()
        twitter_crawler.scrap_twitter_page(driver, url)
        driver.quit()