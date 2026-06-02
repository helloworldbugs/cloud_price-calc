import asyncio
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from config import DISK_OPTIONS, BANDWIDTH_OPTIONS
from region_fetcher import build_country_city_map
import aliyun_provider
import tencent_provider
import huawei_provider

app = FastAPI(title="多云实时比价计算器")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

COUNTRY_CITY_MAP = {}


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
        return {"data": {"specs": [], "disk_options": DISK_OPTIONS, "bandwidth_options": BANDWIDTH_OPTIONS}}

    cities_map = COUNTRY_CITY_MAP[country]
    if city and city != "全部" and city in cities_map:
        target_cities = {city: cities_map[city]}
    else:
        target_cities = cities_map

    all_specs = set()
    for city_name, provider_map in target_cities.items():
        for provider_key, fetch_func in [("tencent", tencent_provider.get_instance_types), ("aliyun", aliyun_provider.get_instance_types), ("huawei", huawei_provider.get_instance_types)]:
            if provider_key in provider_map:
                try:
                    instances = await fetch_func(provider_map[provider_key])
                    for inst in instances:
                        all_specs.add((inst["cpu"], inst["mem"]))
                except:
                    pass

    sorted_specs = sorted(all_specs, key=lambda x: (x[0], x[1]))
    specs_list = [{"cpu": c, "mem": m, "label": f"{c}核{m}G"} for c, m in sorted_specs]
    cpus = sorted(set(c for c, m in sorted_specs))
    mems = sorted(set(m for c, m in sorted_specs))

    return {"data": {"specs": specs_list, "cpus": cpus, "mems": mems, "disk_options": DISK_OPTIONS, "bandwidth_options": BANDWIDTH_OPTIONS}}


@app.post("/api/compare")
async def compare_prices(
    country: str = Query(...),
    city: str = Query("全部"),
    cpu: int = Query(0),
    mem: int = Query(0),
    disk: int = Query(0),
    bandwidth: int = Query(-1),
):
    if country not in COUNTRY_CITY_MAP:
        return {"error": f"不支持的国家: {country}"}

    disk = disk if disk > 0 else 40
    bandwidth = bandwidth if bandwidth >= 0 else 0
    query_all = (cpu <= 0 and mem <= 0)
    filter_cpu = cpu if cpu > 0 else None
    filter_mem = mem if mem > 0 else None

    cities_map = COUNTRY_CITY_MAP[country]
    if city and city != "全部" and city in cities_map:
        target_cities = {city: cities_map[city]}
    else:
        target_cities = cities_map

    all_results = []
    for city_name, provider_map in target_cities.items():
        if filter_cpu and filter_mem:
            tasks = []
            if "aliyun" in provider_map:
                tasks.append(_query_one("阿里云", aliyun_provider.query_price, provider_map["aliyun"], filter_cpu, filter_mem, disk, bandwidth, city_name))
            if "tencent" in provider_map:
                tasks.append(_query_one("腾讯云", tencent_provider.query_price, provider_map["tencent"], filter_cpu, filter_mem, disk, bandwidth, city_name))
            if "huawei" in provider_map:
                tasks.append(_query_one("华为云", huawei_provider.query_price, provider_map["huawei"], filter_cpu, filter_mem, disk, bandwidth, city_name))
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, dict):
                    r["city"] = city_name
                    r["query_cpu"] = filter_cpu
                    r["query_mem"] = filter_mem
                    r["query_disk"] = disk
                    r["query_bw"] = bandwidth
                    all_results.append(r)
        else:
            tasks = []
            if "aliyun" in provider_map:
                tasks.append(aliyun_provider.query_all_prices(provider_map["aliyun"], disk, bandwidth))
            if "tencent" in provider_map:
                tasks.append(tencent_provider.query_all_prices(provider_map["tencent"]))
            if "huawei" in provider_map:
                tasks.append(huawei_provider.query_all_prices(provider_map["huawei"]))
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

    all_results.sort(key=lambda x: x.get("monthly_price", float("inf")))

    seen = set()
    deduped = []
    for r in all_results:
        key = (r.get("provider", ""), r.get("instance_type", ""), r.get("monthly_price", 0))
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    if deduped:
        deduped[0]["is_cheapest"] = True

    return {"data": deduped[:20]}


async def _query_one(provider_name, query_func, region_id, cpu, mem, disk, bandwidth, city_label):
    try:
        r = await query_func(region_id, cpu, mem, disk, bandwidth)
        if isinstance(r, dict):
            r["city"] = city_label
            r["query_cpu"] = cpu
            r["query_mem"] = mem
            r["query_disk"] = disk
            r["query_bw"] = bandwidth
        return r
    except Exception as e:
        return {"provider": provider_name, "error": str(e), "city": city_label}


frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    @app.get("/")
    async def serve_index():
        return FileResponse(os.path.join(frontend_dir, "index.html"))
