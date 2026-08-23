#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
سكربت زحف يومي — نسخة Playwright (متصفح حقيقي مصغّر).

ليش هذا التغيير ضروري: مواقع سلة تبني كروت المنتجات بمكوّن جافاسكربت
اسمه salla-product-card — يعني السعر والاسم ما يكونون موجودين بكود
الصفحة الخام أصلاً، لازم نشغّل متصفح فعلي (Playwright) يخلي الجافاسكربت
يشتغل الأول، وبعدين نقرأ المحتوى المعروض فعليًا على الشاشة.

Google Trends: pytrends غالبًا يُحظر مؤقتًا لما يشتغل من سيرفرات GitHub
(نطاقات IP مشتركة تحظرها جوجل بسهولة) — أضفت إعادة محاولة + تهدئة أطول،
وميّزت بوضوح بين "0 = لا يوجد اهتمام" و null "= تعذر الجلب" بدل ما نعرض
صفر مضلل.
"""

import json
import re
import time
import random
import datetime
from pathlib import Path
from urllib.parse import quote

import requests
from playwright.sync_api import sync_playwright

try:
    from pytrends.request import TrendReq
    HAS_TRENDS = True
except ImportError:
    HAS_TRENDS = False

# ============================================================
# 1) إعدادات المنافسين
#    engine: "playwright" للمواقع اللي تحمّل المنتجات بجافاسكربت (سلة وغيرها)
#            "requests" للمواقع اللي ترجع HTML جاهز من السيرفر مباشرة
# ============================================================
COMPETITORS = [
    {"name": "ppowerstore", "search_url": "https://ppowerstore.com/search?q={q}", "engine": "playwright", "wait_selector": "salla-product-card, .product-item, article"},
    {"name": "mokab", "search_url": "https://mokab.com/ar/search?q={q}", "engine": "playwright", "wait_selector": "salla-product-card, .product-card"},
    {"name": "iblackstores", "search_url": "https://iblackstores.com/ar/search?q={q}", "engine": "playwright", "wait_selector": "salla-product-card, .product-card"},
    {"name": "aletawiksa", "search_url": "https://aletawiksa.com/search?q={q}", "engine": "playwright", "wait_selector": "salla-product-card, .product-card"},
    {"name": "saada", "search_url": "https://saada.sa/ar/search?q={q}", "engine": "playwright", "wait_selector": "salla-product-card, .product-card"},
    {"name": "wjhtektelecome", "search_url": "https://wjhtektelecome.com/ar/search?q={q}", "engine": "playwright", "wait_selector": "salla-product-card, .product-card"},
    {"name": "al3bor-telecom", "search_url": "https://al3bor-telecom.com/search?q={q}", "engine": "playwright", "wait_selector": "salla-product-card, .product-card"},
    {"name": "hope", "search_url": "https://hope.sa/ar/search?q={q}", "engine": "playwright", "wait_selector": "salla-product-card, .product-card"},
    {"name": "alwan7", "search_url": "https://alwan7.com/search?q={q}", "engine": "playwright", "wait_selector": "salla-product-card, .product-card"},
    {"name": "sync", "search_url": "https://sync.sa/ar/search?q={q}", "engine": "playwright", "wait_selector": "salla-product-card, .product-card, article"},
    {"name": "amazon_sa", "search_url": "https://www.amazon.sa/s?k={q}", "engine": "requests", "item_selector": "[data-component-type='s-search-result']", "title_selector": "h2 span", "price_selector": ".a-price .a-offscreen"},
    {"name": "noon", "search_url": "https://www.noon.com/saudi-ar/search/?q={q}", "engine": "playwright", "wait_selector": "[data-qa='product-block']"},
    {"name": "jarir", "search_url": "https://www.jarir.com/sa-en/catalogsearch/result/?q={q}", "engine": "playwright", "wait_selector": ".product-item"},
    {"name": "extra", "search_url": "https://www.extra.com/ar-sa/search/?q={q}", "engine": "playwright", "wait_selector": ".product-container, .product"},
]

WATCHLIST = [
    {"query": "جودا 20000", "category": "بطاريات متنقلة", "label": "بطارية جودا 20000mAh"},
    {"query": "جودا هاربو", "category": "منصات ومحطات شحن", "label": "منصة جودا هاربو لشحن البطاريات"},
    {"query": "جودا فولت لينك", "category": "توصيلات كهربائية", "label": "توصيلة جودا فولت لينك"},
    {"query": "جودا AirVolt", "category": "منتجات السيارة", "label": "مضخة هواء جودا AirVolt"},
    {"query": "راف باور باور بانك", "category": "بطاريات متنقلة", "label": "بطارية راف باور"},
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}

OUTPUT_FILE = Path(__file__).resolve().parent.parent / "data" / "products.json"

PRICE_PATTERN = re.compile(r"(\d{1,4}(?:[.,]\d{1,2})?)\s*(?:ر\.?\s*س|SAR|ريال)", re.IGNORECASE)


def clean_price(text: str):
    digits = "".join(c for c in text if c.isdigit() or c == ".")
    try:
        return float(digits) if digits else None
    except ValueError:
        return None


def extract_price_from_text(text: str):
    m = PRICE_PATTERN.search(text)
    if m:
        try:
            return float(m.group(1).replace(",", "."))
        except ValueError:
            return None
    return None


def scrape_requests(competitor: dict, query: str):
    url = competitor["search_url"].format(q=requests.utils.quote(query))
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  ⚠ فشل الاتصال بـ {competitor['name']}: {e}")
        return None
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(resp.text, "html.parser")
    item = soup.select_one(competitor["item_selector"])
    if not item:
        return None
    title_el = item.select_one(competitor["title_selector"])
    price_el = item.select_one(competitor["price_selector"])
    return {
        "found": True,
        "title": title_el.get_text(strip=True) if title_el else None,
        "price": clean_price(price_el.get_text(strip=True)) if price_el else None,
    }


def scrape_playwright(page, competitor: dict, query: str):
    url = competitor["search_url"].format(q=quote(query))
    try:
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
    except Exception as e:
        print(f"  ⚠ فشل فتح الصفحة عند {competitor['name']}: {e}")
        return None

    wait_sel = competitor.get("wait_selector", "body")
    try:
        page.wait_for_selector(wait_sel, timeout=10000)
    except Exception:
        page.wait_for_timeout(2500)

    try:
        first_card = page.locator(wait_sel).first
        if first_card.count() == 0:
            return None
        card_text = first_card.inner_text(timeout=5000)
    except Exception:
        return None

    if not card_text or len(card_text.strip()) < 3:
        return None

    price = extract_price_from_text(card_text)
    title_line = next((ln.strip() for ln in card_text.splitlines() if ln.strip()), None)

    return {"found": True, "title": title_line, "price": price}


def get_trend_interest(keywords, geo="SA"):
    if not HAS_TRENDS:
        return {}
    results = {}
    for kw in keywords:
        success = False
        for attempt in range(3):
            try:
                pytrends = TrendReq(hl="ar-SA", tz=180, retries=2, backoff_factor=0.5)
                pytrends.build_payload([kw], timeframe="today 12-m", geo=geo)
                df = pytrends.interest_over_time()
                if not df.empty and kw in df.columns:
                    results[kw] = int(df[kw].mean())
                    success = True
                break
            except Exception as e:
                wait = random.uniform(8, 15) * (attempt + 1)
                print(f"  ⚠ Trends محاولة {attempt+1} فشلت لـ '{kw}' ({e}) — إعادة محاولة بعد {wait:.0f} ثانية")
                time.sleep(wait)
        if not success:
            results[kw] = None
        time.sleep(random.uniform(5, 9))
    return results


def main():
    print(f"🚀 بدء الزحف اليومي (Playwright) — {datetime.datetime.now().isoformat()}")

    trend_scores = get_trend_interest([w["query"] for w in WATCHLIST])

    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=HEADERS["User-Agent"],
            locale="ar-SA",
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()

        for w in WATCHLIST:
            print(f"\n🔍 {w['label']} ({w['query']})")
            found_at = []
            prices = []

            for comp in COMPETITORS:
                if comp["engine"] == "requests":
                    r = scrape_requests(comp, w["query"])
                else:
                    r = scrape_playwright(page, comp, w["query"])

                time.sleep(random.uniform(2, 4))

                if r and r.get("found") and r.get("price"):
                    found_at.append(comp["name"])
                    prices.append(r["price"])
                    print(f"  ✓ {comp['name']}: {r['price']} ر.س — {r.get('title')}")
                else:
                    print(f"  — {comp['name']}: ما لقينا نتيجة")

            trend_val = trend_scores.get(w["query"])
            results.append({
                "id": w["query"].replace(" ", "_"),
                "cat": w["category"],
                "name": w["label"],
                "query": w["query"],
                "competitorsCount": len(found_at),
                "competitorsList": ", ".join(found_at) if found_at else "",
                "minPrice": min(prices) if prices else None,
                "avgPrice": round(sum(prices) / len(prices), 1) if prices else None,
                "trendInterest": trend_val,
                "trendStatus": "متاح" if trend_val is not None else "تعذر الجلب (حظر مؤقت من جوجل، طبيعي أحيانًا)",
                "updated": datetime.date.today().isoformat(),
            })

        browser.close()

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n✅ تم الحفظ بـ {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
