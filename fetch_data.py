"""
투자 지표 대시보드 데이터 수집 스크립트
- GitHub Actions가 하루 한 번 실행해서 docs/data.js 를 갱신합니다.
- 어떤 소스가 실패하면 직전 데이터를 그대로 두고(stale 표시) 나머지만 갱신합니다.

소스
  야후 파이낸스(yfinance): 나스닥, S&P500, VIX, 미 3개월(13주) 국채, 미 10년물, WTI/브렌트, M7
  FRED(무료, 키 불필요): 야후 실패 시 지수/금리/유가 백업
  CNN: 공포탐욕지수
  한국은행 ECOS(무료 API 키 필요, ECOS_API_KEY): KOFR
"""
import io
import json
import os
import time
import datetime as dt
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "docs" / "data.js"
YEARS = 6  # 차트에 싣는 기간(전고점 계산은 전체 기간 기준)
TODAY = dt.date.today()
START = TODAY - dt.timedelta(days=365 * YEARS + 10)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)

# key: (이름, 단위, 야후 티커, FRED 시리즈, 소수점)
YF_SERIES = {
    "nasdaq": ("나스닥 종합", "pt", "^IXIC", "NASDAQCOM", 2),
    "sp500": ("S&P 500", "pt", "^GSPC", "SP500", 2),
    "vix": ("VIX", "", "^VIX", "VIXCLS", 2),
    "us3m": ("미국 3개월 국채", "%", "^IRX", "DTB3", 3),
    "us10y": ("미국 10년물", "%", "^TNX", "DGS10", 3),
    "wti": ("WTI 유가", "$", "CL=F", "DCOILWTICO", 2),
    "brent": ("브렌트 유가", "$", "BZ=F", "DCOILBRENTEU", 2),
}
M7 = {
    "AAPL": "애플",
    "MSFT": "마이크로소프트",
    "NVDA": "엔비디아",
    "GOOGL": "알파벳",
    "AMZN": "아마존",
    "META": "메타",
    "TSLA": "테슬라",
}


def log(*a):
    print("[fetch]", *a, flush=True)


def load_previous():
    if not OUT.exists():
        return {}
    txt = OUT.read_text(encoding="utf-8").strip()
    try:
        body = txt[txt.index("{"): txt.rindex("}") + 1]
        return json.loads(body).get("series", {})
    except Exception as e:  # noqa
        log("이전 데이터 읽기 실패:", e)
        return {}


def to_series_dict(s: pd.Series, digits: int, with_ath: bool):
    """전체 이력 Series -> 최근 YEARS년 + 전고점(running max, 전체 이력 기준)"""
    s = s.dropna()
    s = s[~s.index.duplicated(keep="last")].sort_index()
    if s.empty:
        raise ValueError("빈 데이터")
    ath = s.cummax()
    mask = s.index.date >= START
    s2, ath2 = s[mask], ath[mask]
    d = {
        "dates": [i.strftime("%Y-%m-%d") for i in s2.index],
        "values": [round(float(v), digits) for v in s2.values],
        "asof": s2.index[-1].strftime("%Y-%m-%d"),
    }
    if with_ath:
        d["ath"] = [round(float(v), digits) for v in ath2.values]
        d["athAll"] = round(float(ath.iloc[-1]), digits)
        d["athDate"] = s.idxmax().strftime("%Y-%m-%d")
    return d


# ---------------- 야후 ----------------
def yf_history(ticker: str) -> pd.Series:
    import yfinance as yf

    last_err = None
    for attempt in range(3):
        try:
            df = yf.Ticker(ticker).history(period="max", interval="1d", auto_adjust=True)
            if df is not None and not df.empty:
                s = df["Close"]
                s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
                return s
            last_err = "빈 응답"
        except Exception as e:  # noqa
            last_err = e
        time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"yfinance {ticker} 실패: {last_err}")


# ---------------- FRED ----------------
def fred_history(sid: str) -> pd.Series:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.set_index("date")["value"].dropna()


def fix_rate_scale(s: pd.Series) -> pd.Series:
    # 예전 야후 ^TNX/^IRX는 x10 스케일인 경우가 있어 보정
    return s / 10 if s.tail(250).median() > 25 else s


# ---------------- CNN 공포탐욕 ----------------
def fear_greed(prev):
    start = (TODAY - dt.timedelta(days=365 * YEARS)).isoformat()
    url = f"https://production.dataviz.cnn.io/index/fearandgreed/graphdata/{start}"
    headers = {
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://edition.cnn.com/",
        "Origin": "https://edition.cnn.com",
    }
    r = requests.get(url, headers=headers, timeout=60)
    r.raise_for_status()
    j = r.json()
    pts = {}
    # 기존 누적 이력 유지
    if prev:
        pts.update(dict(zip(prev["dates"], prev["values"])))
    for p in j["fear_and_greed_historical"]["data"]:
        d = dt.datetime.fromtimestamp(p["x"] / 1000, dt.timezone.utc).strftime("%Y-%m-%d")
        pts[d] = round(float(p["y"]), 1)
    cur = j.get("fear_and_greed", {})
    if cur.get("score") is not None and cur.get("timestamp"):
        d = pd.to_datetime(cur["timestamp"]).strftime("%Y-%m-%d")
        pts[d] = round(float(cur["score"]), 1)
    keys = sorted(k for k in pts if k >= START.isoformat())
    return {"dates": keys, "values": [pts[k] for k in keys], "asof": keys[-1]}


# ---------------- 한국은행 ECOS: KOFR ----------------
def ecos_get(key, path):
    url = f"https://ecos.bok.or.kr/api/{path.format(key=key)}"
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.json()


def kofr():
    key = os.environ.get("ECOS_API_KEY", "").strip()
    if not key:
        raise RuntimeError("ECOS_API_KEY 미설정 (README 참고)")
    stat = os.environ.get("KOFR_STAT_CODE", "").strip()
    item = os.environ.get("KOFR_ITEM_CODE", "").strip()

    if not (stat and item):
        candidates = [stat] if stat else ["817Y002"]
        found = None
        for sc in candidates:
            try:
                rows = ecos_get(key, "StatisticItemList/{key}/json/kr/1/500/" + sc)["StatisticItemList"]["row"]
                for row in rows:
                    if "KOFR" in row.get("ITEM_NAME", "").upper() and row.get("CYCLE") == "D":
                        found = (sc, row["ITEM_CODE"])
                        break
            except Exception as e:  # noqa
                log("ECOS 항목 조회 실패", sc, e)
            if found:
                break
        if not found:
            # 통계표 전체 목록에서 KOFR 검색
            tables = ecos_get(key, "StatisticTableList/{key}/json/kr/1/10000")["StatisticTableList"]["row"]
            for t in tables:
                if "KOFR" in t.get("STAT_NAME", "").upper() and t.get("CYCLE") == "D":
                    rows = ecos_get(key, "StatisticItemList/{key}/json/kr/1/500/" + t["STAT_CODE"])["StatisticItemList"]["row"]
                    for row in rows:
                        if "KOFR" in row.get("ITEM_NAME", "").upper():
                            found = (t["STAT_CODE"], row["ITEM_CODE"])
                            break
                if found:
                    break
        if not found:
            raise RuntimeError("ECOS에서 KOFR 통계를 찾지 못함 (KOFR_STAT_CODE/KOFR_ITEM_CODE 직접 지정 가능)")
        stat, item = found
        log("KOFR 통계코드", stat, item)

    path = (
        "StatisticSearch/{key}/json/kr/1/100000/"
        f"{stat}/D/{START.strftime('%Y%m%d')}/{TODAY.strftime('%Y%m%d')}/{item}"
    )
    rows = ecos_get(key, path)["StatisticSearch"]["row"]
    s = pd.Series(
        {pd.to_datetime(r["TIME"]): float(r["DATA_VALUE"]) for r in rows if r.get("DATA_VALUE") not in (None, "")}
    )
    return to_series_dict(s, 3, with_ath=False)


# ---------------- main ----------------
def main():
    prev = load_previous()
    out = {}

    def keep_prev(key, err, meta):
        if key in prev:
            d = dict(prev[key])
            d.update(meta)
            d["stale"] = True
            d["error"] = str(err)[:300]
            out[key] = d
        else:
            out[key] = dict(meta, error=str(err)[:300], dates=[], values=[])
        log(f"{key}: 실패 -> {'직전 데이터 유지' if key in prev else '데이터 없음'} ({err})")

    for key, (name, unit, yft, fred, digits) in YF_SERIES.items():
        meta = {"name": name, "unit": unit}
        with_ath = key in ("nasdaq", "sp500")
        try:
            s = yf_history(yft)
            if key in ("us3m", "us10y"):
                s = fix_rate_scale(s)
            d = to_series_dict(s, digits, with_ath)
            d["source"] = f"Yahoo Finance ({yft})"
        except Exception as e1:
            log(key, "야후 실패, FRED 시도:", e1)
            try:
                d = to_series_dict(fred_history(fred), digits, with_ath)
                d["source"] = f"FRED ({fred})"
            except Exception as e2:
                keep_prev(key, f"{e1} / {e2}", meta)
                continue
        d.update(meta)
        out[key] = d
        log(key, "OK", d["asof"], d["values"][-1])

    for tk, name in M7.items():
        key = "m7_" + tk
        meta = {"name": name, "ticker": tk, "unit": "$"}
        try:
            d = to_series_dict(yf_history(tk), 2, with_ath=True)
            d["source"] = f"Yahoo Finance ({tk}, 수정주가)"
            d.update(meta)
            out[key] = d
            log(key, "OK", d["asof"], d["values"][-1])
        except Exception as e:
            keep_prev(key, e, meta)

    meta = {"name": "공포탐욕지수", "unit": ""}
    try:
        d = fear_greed(prev.get("feargreed"))
        d["source"] = "CNN Fear & Greed Index"
        d.update(meta)
        out["feargreed"] = d
        log("feargreed OK", d["asof"], d["values"][-1])
    except Exception as e:
        keep_prev("feargreed", e, meta)

    meta = {"name": "KOFR", "unit": "%"}
    try:
        d = kofr()
        d["source"] = "한국은행 ECOS (KOFR)"
        d.update(meta)
        out["kofr"] = d
        log("kofr OK", d["asof"], d["values"][-1])
    except Exception as e:
        keep_prev("kofr", e, meta)

    payload = {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "series": out,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        "window.DASH_DATA = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )
    ok = sum(1 for v in out.values() if not v.get("error"))
    log(f"완료: {ok}/{len(out)} 성공 -> {OUT}")


if __name__ == "__main__":
    main()
