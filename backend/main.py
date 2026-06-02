import asyncio
import logging
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from region_fetcher import build_country_city_map
import aliyun_provider
import tencent_provider
import huawei_provider

logger = logging.getLogger(__name__)

app = FastAPI(title="多云实时比价计算器")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

COUNTRY_CITY_MAP = {}


def _region_ids(provider_map: dict, provider_key: str) -> list:
    value = provider_map.get(provider_key)
    if not value:
        return []
    if isinstance(value, list):
        return value
    return [value]


@app.on_event("startup")
async def startup():
    global COUNTRY_CITY_MAP
    COUNTRY_CITY_MAP = await build_country_city_map()


@app.get("/api/countries")
async def get_countries():
    result = []
    for country, cities in COUNTRY_CITY_MAP.items():
        city_list = []
        for city_name, providers in cities.items():
            city_list.append({"name": city_name, "providers": providers})
        result.append({"country": country, "cities": city_list})
    return {"data": result}


@app.get("/api/specs")
async def get_specs(country: str = Query("中国"), city: str = Query("")):
    if country not in COUNTRY_CITY_MAP:
        return {"data": {"specs": []}}

    cities_map = COUNTRY_CITY_MAP[country]
    if city and city != "全部" and city in cities_map:
        target_cities = {city: cities_map[city]}
    else:
        target_cities = cities_map

    all_specs = set()
    for city_name, provider_map in target_cities.items():
        for provider_key, fetch_func in [("tencent", tencent_provider.get_instance_types), ("aliyun", aliyun_provider.get_instance_types), ("huawei", huawei_provider.get_instance_types)]:
            for region_id in _region_ids(provider_map, provider_key):
                try:
                    instances = await fetch_func(region_id)
                    for inst in instances:
                        all_specs.add((inst["cpu"], inst["mem"]))
                except Exception:
                    logger.exception("Failed to fetch specs: provider=%s region=%s", provider_key, region_id)

    sorted_specs = sorted(all_specs, key=lambda x: (x[0], x[1]))
    specs_list = [{"cpu": c, "mem": m, "label": f"{c}核{m}G"} for c, m in sorted_specs]
    cpus = sorted(set(c for c, m in sorted_specs))
    mems = sorted(set(m for c, m in sorted_specs))

    return {"data": {"specs": specs_list, "cpus": cpus, "mems": mems}}


@app.post("/api/compare")
async def compare_prices(
    country: str = Query(...),
    city: str = Query("全部"),
    cpu: int = Query(0),
    mem: int = Query(0),
):
    if country not in COUNTRY_CITY_MAP:
        return {"error": f"不支持的国家: {country}"}

    query_all = (cpu <= 0 and mem <= 0)
    filter_cpu = cpu if cpu > 0 else None
    filter_mem = mem if mem > 0 else None

    cities_map = COUNTRY_CITY_MAP[country]
    if city and city != "全部":
        if city not in cities_map:
            return {"error": f"不支持的城市: {city}"}
        target_cities = {city: cities_map[city]}
    else:
        target_cities = cities_map

    provider_has_region = {"阿里云": False, "腾讯云": False, "华为云": False}
    all_results = []
    for city_name, provider_map in target_cities.items():
        if _region_ids(provider_map, "aliyun"):
            provider_has_region["阿里云"] = True
        if _region_ids(provider_map, "tencent"):
            provider_has_region["腾讯云"] = True
        if _region_ids(provider_map, "huawei"):
            provider_has_region["华为云"] = True

        if filter_cpu and filter_mem:
            tasks = []
            for region_id in _region_ids(provider_map, "aliyun"):
                tasks.append(_query_one("阿里云", aliyun_provider.query_price, region_id, filter_cpu, filter_mem, city_name))
            for region_id in _region_ids(provider_map, "tencent"):
                tasks.append(_query_one("腾讯云", tencent_provider.query_price, region_id, filter_cpu, filter_mem, city_name))
            for region_id in _region_ids(provider_map, "huawei"):
                tasks.append(_query_one("华为云", huawei_provider.query_price, region_id, filter_cpu, filter_mem, city_name))
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, dict):
                    r["city"] = city_name
                    r["query_cpu"] = filter_cpu
                    r["query_mem"] = filter_mem
                    all_results.append(r)
        else:
            tasks = []
            for region_id in _region_ids(provider_map, "aliyun"):
                tasks.append(aliyun_provider.query_all_prices(region_id))
            for region_id in _region_ids(provider_map, "tencent"):
                tasks.append(tencent_provider.query_all_prices(region_id))
            for region_id in _region_ids(provider_map, "huawei"):
                tasks.append(huawei_provider.query_all_prices(region_id))
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, list):
                    for item in r:
                        item["city"] = city_name
                    all_results.extend(r)

    if filter_cpu and not filter_mem:
        all_results = [r for r in all_results if r.get("cpu") == filter_cpu]
    if filter_mem and not filter_cpu:
        all_results = [r for r in all_results if r.get("mem") == filter_mem]

    all_results.sort(key=lambda x: (x.get("error") is not None, x.get("monthly_price", float("inf"))))

    seen = set()
    deduped = []
    for r in all_results:
        key = (r.get("provider", ""), r.get("region_id", ""), r.get("instance_type", ""), r.get("monthly_price", 0))
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    comparable = [r for r in deduped if not r.get("error")]
    if comparable:
        comparable[0]["is_cheapest"] = True

    return {"data": deduped[:20], "providers": provider_has_region}


async def _query_one(provider_name, query_func, region_id, cpu, mem, city_label):
    try:
        r = await query_func(region_id, cpu, mem)
        if isinstance(r, dict):
            r["city"] = city_label
            r["query_cpu"] = cpu
            r["query_mem"] = mem
        return r
    except Exception as e:
        logger.exception("Price query failed: provider=%s region=%s", provider_name, region_id)
        return {"provider": provider_name, "error": str(e), "city": city_label}


frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    @app.get("/")
    async def serve_index():
        return FileResponse(os.path.join(frontend_dir, "index.html"))
