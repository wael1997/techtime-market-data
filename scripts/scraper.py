#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
سكربت زحف يومي — يجمع أسعار المنافسين وبيانات اهتمام البحث (Google Trends)
ويحفظها بملف data/products.json ليقرأه تطبيق TechTime Growth OS مباشرة.

مهم / اقرأ هذا أول:
- كل موقع منافس له بنية HTML مختلفة، فلازم تضبط الـ SELECTORS تحت لكل موقع
  بنفسك (خطوات "كيف تلاقي الـ selector الصح" موجودة بملف README.md).
- هذا القالب جاهز فعليًا لموقعين (ppowerstore, mokab) كمثال يعمل، وباقي
  المواقع فيها إعدادات تقريبية تحتاج تعديل بسيط بعد أول تشغيل فعلي.
- pytrends مكتبة غير رسمية — أحيانًا تتوقف مؤقتًا (Rate Limit) من جوجل،
  السكربت مصمم يتجاوز هذا بصمت (يترك القيمة فارغة) بدل ما يوقف كل شي.
"""

import json
import time
import random
import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

try:
    from pytrends.request import TrendReq
    HAS_TRENDS = True
except ImportError:
    HAS_TRENDS = False

# ============================================================
# 1) إعدادات المنافسين — أضيفوا/عدّلوا حسب الحاجة
# ============================================================
# search_url: {q} تنستبدل باسم المنتج/الكلمة اللي نبحث عنها
# selectors: CSS selectors لاستخراج اسم المنتج والسعر من نتائج البحث
#            (شوفوا README.md لطريقة إيجادها بمتصفحكم عبر "فحص العنصر")

COMPETITORS = [
    {
        "name": "ppowerstore",
        "search_url": "https://ppowerstore.com/search?q={q}",
        "item_selector": ".product-item, .grid-product, article.product",
        "title_selector": ".product-item__title, .grid-product__title, h3",
        "price_selector": ".price, .product-item__price, .money",
        "confidence": "متوسطة — تم تصفح الموقع فعليًا خلال البحث، لكن السيلكتورز تقديرية",
    },
    {
        "name": "mokab",
        "search_url": "https://mokab.com/ar/search?q={q}",
        "item_selector": ".product-card, .s-product-card",
        "title_selector": ".product-card__title, .s-product-card__name",
        "price_selector": ".product-card__price, .s-product-card__price",
        "confidence": "متوسطة — منصة سلة (Salla)، نفس بنية techtimesa تقريبًا",
    },
    {
        "name": "iblackstores",
        "search_url": "https://iblackstores.com/ar/search?q={q}",
        "item_selector": ".product-card, .s-product-card, .product-item",
        "title_selector": ".product-card__title, .s-product-card__name, h3",
        "price_selector": ".product-card__price, .s-product-card__price, .price",
        "confidence": "منخفضة — منصة سلة، لم يُختبر مباشرة، قد يحتاج تعديل selector",
    },
    {
        "name": "aletawiksa",
        "search_url": "https://aletawiksa.com/search?q={q}",
        "item_selector": ".product-card, .s-product-card, .product-item",
        "title_selector": ".product-card__title, .s-product-card__name, h3",
        "price_selector": ".product-card__price, .s-product-card__price, .price",
        "confidence": "منخفضة — منصة سلة، تقديري",
    },
    {
        "name": "saada",
        "search_url": "https://saada.sa/ar/search?q={q}",
        "item_selector": ".product-card, .s-product-card, .product-item",
        "title_selector": ".product-card__title, .s-product-card__name, h3",
        "price_selector": ".product-card__price, .s-product-card__price, .price",
        "confidence": "منخفضة — منصة سلة، تقديري",
    },
    {
        "name": "wjhtektelecome",
        "search_url": "https://wjhtektelecome.com/ar/search?q={q}",
        "item_selector": ".product-card, .s-product-card, .product-item",
        "title_selector": ".product-card__title, .s-product-card__name, h3",
        "price_selector": ".product-card__price, .s-product-card__price, .price",
        "confidence": "منخفضة — منصة سلة، تقديري",
    },
    {
        "name": "al3bor-telecom",
        "search_url": "https://al3bor-telecom.com/search?q={q}",
        "item_selector": ".product-card, .s-product-card, .product-item",
        "title_selector": ".product-card__title, .s-product-card__name, h3",
        "price_selector": ".product-card__price, .s-product-card__price, .price",
        "confidence": "منخفضة — تقديري، منصة غير مؤكدة",
    },
    {
        "name": "hope",
        "search_url": "https://hope.sa/ar/search?q={q}",
        "item_selector": ".product-card, .s-product-card, .product-item",
        "title_selector": ".product-card__title, .s-product-card__name, h3",
        "price_selector": ".product-card__price, .s-product-card__price, .price",
        "confidence": "منخفضة — منصة سلة، تقديري",
    },
    {
        "name": "alwan7",
        "search_url": "https://alwan7.com/search?q={q}",
        "item_selector": ".product-card, .s-product-card, .product-item",
        "title_selector": ".product-card__title, .s-product-card__name, h3",
        "price_selector": ".product-card__price, .s-product-card__price, .price",
        "confidence": "منخفضة — منصة سلة، تقديري",
    },
    {
        "name": "sync",
        "search_url": "https://sync.sa/ar/search?q={q}",
        "item_selector": ".product-card, .product-item, article",
        "title_selector": ".product-card__title, h3, .product-title",
        "price_selector": ".product-card__price, .price, .money",
        "confidence": "منخفضة — تقديري",
    },
    # ⚠️ المتاجر الكبرى التالية (Amazon, Noon, Jarir, Extra) عندها حماية قوية
    # ضد الزحف الآلي (Anti-bot / Captcha) — الزحف البسيط بـ requests غالبًا
    # يفشل أو يُحظر. تحتاج Playwright + إعدادات إضافية، والنتيجة غير مضمونة
    # حتى بعد التعديل. أضفناها هنا كقالب جاهز لو حبيتوا تجربونها لاحقًا.
    {
        "name": "amazon_sa",
        "search_url": "https://www.amazon.sa/s?k={q}",
        "item_selector": "[data-component-type='s-search-result']",
        "title_selector": "h2 span",
        "price_selector": ".a-price .a-offscreen",
        "confidence": "منخفضة جدًا — حماية قوية ضد الزحف، النتائج غير مضمونة",
    },
    {
        "name": "noon",
        "search_url": "https://www.noon.com/saudi-ar/search/?q={q}",
        "item_selector": "[data-qa='product-block']",
        "title_selector": "[data-qa='product-name']",
        "price_selector": "[data-qa='product-price']",
        "confidence": "منخفضة جدًا — موقع React ثقيل + حماية، يحتاج Playwright غالبًا",
    },
    {
        "name": "jarir",
        "search_url": "https://www.jarir.com/sa-en/catalogsearch/result/?q={q}",
        "item_selector": ".product-item",
        "title_selector": ".product-item-link",
        "price_selector": ".price",
        "confidence": "منخفضة جدًا — حماية ضد الزحف، النتائج غير مضمونة",
    },
    {
        "name": "extra",
        "search_url": "https://www.extra.com/ar-sa/search/?q={q}",
        "item_selector": ".product-container, .product",
        "title_selector": ".product-title, .name",
        "price_selector": ".price, .product-price",
        "confidence": "منخفضة جدًا — موقع React ثقيل، يحتاج Playwright غالبًا",
    },
]

# الكلمات/المنتجات اللي نراقبها — عدّلوا هذي القائمة بحرية
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


def clean_price(text: str):
    """يستخرج أول رقم من نص السعر (مثال: '109.00 ر.س' -> 109.0)."""
    digits = "".join(c for c in text if c.isdigit() or c == ".")
    try:
        return float(digits) if digits else None
    except ValueError:
        return None


def scrape_competitor(competitor: dict, query: str):
    """يبحث عن كلمة معينة عند منافس واحد ويرجع أول نتيجة (اسم + سعر)."""
    url = competitor["search_url"].format(q=requests.utils.quote(query))
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  ⚠ فشل الاتصال بـ {competitor['name']}: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    item = soup.select_one(competitor["item_selector"])
    if not item:
        # ملاحظة: أغلب مواقع Salla تحمّل المنتجات عبر JavaScript، فالبحث
        # البسيط بـ requests ممكن يرجع صفحة فاضية. راجعوا README.md
        # لخيار استخدام Playwright بدل requests لهذي الحالة.
        return None

    title_el = item.select_one(competitor["title_selector"])
    price_el = item.select_one(competitor["price_selector"])

    return {
        "found": True,
        "title": title_el.get_text(strip=True) if title_el else None,
        "price": clean_price(price_el.get_text(strip=True)) if price_el else None,
        "source": competitor["name"],
        "url": url,
    }


def get_trend_interest(keywords, geo="SA"):
    """يرجع درجة اهتمام نسبية 0-100 من Google Trends لكل كلمة (السعودية)."""
    if not HAS_TRENDS:
        return {}
    results = {}
    try:
        pytrends = TrendReq(hl="ar-SA", tz=180)
        # يُرسل بمجموعات من 5 كلمات كحد أقصى (قيد جوجل نفسه)
        for i in range(0, len(keywords), 5):
            batch = keywords[i:i + 5]
            pytrends.build_payload(batch, timeframe="today 12-m", geo=geo)
            df = pytrends.interest_over_time()
            if not df.empty:
                for kw in batch:
                    if kw in df.columns:
                        results[kw] = int(df[kw].mean())
            time.sleep(random.uniform(2, 4))  # تهدئة الطلبات لتفادي الحظر المؤقت
    except Exception as e:
        print(f"  ⚠ تعذّر جلب بيانات Trends (طبيعي أحيانًا، جوجل يحد الطلبات): {e}")
    return results


def main():
    print(f"🚀 بدء الزحف اليومي — {datetime.datetime.now().isoformat()}")

    trend_scores = get_trend_interest([w["query"] for w in WATCHLIST])

    results = []
    for w in WATCHLIST:
        print(f"\n🔍 {w['label']} ({w['query']})")
        found_at = []
        prices = []

        for comp in COMPETITORS:
            r = scrape_competitor(comp, w["query"])
            time.sleep(random.uniform(1.5, 3))  # تهدئة بين الطلبات، احترام الموقع
            if r and r.get("found") and r.get("price"):
                found_at.append(comp["name"])
                prices.append(r["price"])
                print(f"  ✓ {comp['name']}: {r['price']} ر.س — {r['title']}")
            else:
                conf = comp.get("confidence", "")
                print(f"  — {comp['name']}: ما لقينا نتيجة ({conf})")

        results.append({
            "id": w["query"].replace(" ", "_"),
            "cat": w["category"],
            "name": w["label"],
            "query": w["query"],
            "competitorsCount": len(found_at),
            "competitorsList": ", ".join(found_at) if found_at else "",
            "minPrice": min(prices) if prices else None,
            "avgPrice": round(sum(prices) / len(prices), 1) if prices else None,
            "trendInterest": trend_scores.get(w["query"]),
            "updated": datetime.date.today().isoformat(),
        })

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n✅ تم الحفظ بـ {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
