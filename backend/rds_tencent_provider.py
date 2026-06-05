import httpx
import asyncio
import logging

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
    "Origin": "https://buy.cloud.tencent.com",
    "Referer": "https://buy.cloud.tencent.com/price/cdb",
    "x-referer": "https://buy.cloud.tencent.com/price/cdb",
    "x-csrf-token": "",
}

TENCENT_CDB_REGION_IDS = {
    "ap-guangzhou": 1,
    "ap-shanghai": 4,
    "ap-beijing": 8,
    "ap-chengdu": 16,
    "ap-chongqing": 19,
    "ap-hongkong": 5,
    "ap-singapore": 9,
    "ap-tokyo": 25,
    "ap-seoul": 18,
    "ap-bangkok": 23,
    "ap-jakarta": 14,
    "ap-mumbai": 21,
    "na-siliconvalley": 15,
    "na-ashburn": 22,
    "na-toronto": 27,
    "eu-frankfurt": 17,
    "eu-moscow": 11,
    "sa-saopaulo": 28,
    "ap-taipei": 7,
    "ap-nanjing": 33,
    "ap-shenzhen": 37,
    "ap-tianjin": 36,
    "ap-beijing-fsi": 46,
    "ap-shanghai-fsi": 45,
    "ap-shenzhen-fsi": 47,
}

_client = None
_instance_cache = {}
_zone_cache = {}


async def _get_client():
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=30, follow_redirects=True)
    return _client


async def _get_region_configs(region: str):
    client = await _get_client()
    url = "https://cdb.cloud.tencent.com/api/server-cloud3/supeross/biz.mysql.DescribeCdbZoneConfig"
    body = {"Region": region, "ApiModule": "cdb", "mc_gtk": ""}
    try:
        resp = await client.post(url, headers=HEADERS, json=body, timeout=15)
        data = resp.json()
        if data.get("code") == 0:
            configs = data.get("data", {}).get("DataResult", {}).get("Configs", [])
            result = []
            for c in configs:
                cpu = c.get("Cpu", 0)
                mem_mb = c.get("Memory", 0)
                device = c.get("Device", "")
                device_type = c.get("DeviceType", "")
                config_id = c.get("Id", 0)
                if cpu > 0 and mem_mb > 0 and device == "Z3":
                    mem_gb = mem_mb // 1000
                    result.append({
                        "cpu": cpu,
                        "mem": mem_gb,
                        "config_id": config_id,
                        "device_type": device_type,
                        "instance_type": f"CDB-{device_type}-{cpu}C{mem_gb}G",
                    })
            return result
    except Exception:
        logger.exception("Failed to fetch Tencent CDB configs for region %s", region)
    return []


async def _get_zone_for_region(region: str):
    if region in _zone_cache:
        return _zone_cache[region]
    client = await _get_client()
    url = "https://cdb.cloud.tencent.com/api/server-cloud3/supeross/biz.mysql.DescribeZone"
    body = {"Region": region, "ApiModule": "cdb", "mc_gtk": ""}
    try:
        resp = await client.post(url, headers=HEADERS, json=body, timeout=15)
        data = resp.json()
        if data.get("code") == 0:
            zones = data.get("data", {}).get("Zones", [])
            for z in zones:
                if not z.get("IsSaleOut") and z.get("SupportDeviceTypes"):
                    zone_id = z.get("ZoneId", 0)
                    _zone_cache[region] = zone_id
                    return zone_id
    except Exception:
        logger.exception("Failed to fetch Tencent CDB zones for region %s", region)
    return 0


async def _get_region_id(region: str) -> int:
    if region in TENCENT_CDB_REGION_IDS:
        return TENCENT_CDB_REGION_IDS[region]
    return 1


async def _query_prices_for_specs(region: str, zone_id: int, specs: list):
    if not specs:
        return {}
    region_id = await _get_region_id(region)
    if region_id == 0:
        return {}

    res_info = []
    for s in specs:
        mem_mb = s["mem"] * 1000
        bill_code = s["cpu"] * 100000 + s["mem"] * 1000
        res_info.append({
            "type": "cdb",
            "goodsCategoryId": 100016,
            "regionId": region_id,
            "zoneId": zone_id,
            "goodsDetail": {
                "productCode": "p_cdb",
                "subProductCode": "sp_cdb_master",
                "pid": 1000750,
                "ladder": 0,
                "sv_cdb_cpu_master": s["cpu"],
                "sv_cdb_mem_master": mem_mb,
                "timeSpan": 1,
                "timeUnit": "m",
                "subType": "CUSTOM",
                "payType": 0,
                "mem": mem_mb,
                "billCode": bill_code,
                "cpu": s["cpu"],
                "cdbMem": mem_mb,
                "engineType": "InnoDB",
                "protectMode": None,
                "disk": 0,
                "cdbVolume": 0,
            },
            "goodsNum": 1,
            "payMode": 1,
            "currency": "CNY",
        })

    client = await _get_client()
    url = "https://cdb.cloud.tencent.com/api/server-cgw/trade/qcloud.Price.multiGetPrice"
    body = {"regionId": region_id, "resInfo": res_info}
    try:
        resp = await client.post(url, headers=HEADERS, json=body, timeout=15)
        data = resp.json()
        if data.get("code") == 0:
            prices = data.get("data", [])
            results = {}
            for i, spec in enumerate(specs):
                if i < len(prices):
                    p = prices[i]
                    price_yuan = round(float(p.get("price", 0)) / 100, 2)
                    results[(spec["cpu"], spec["mem"])] = price_yuan
            return results
    except Exception:
        logger.exception("Failed to query Tencent CDB prices for region %s", region)
    return {}


async def get_instance_types(region_id: str) -> list:
    if region_id in _instance_cache:
        return _instance_cache[region_id]
    configs = await _get_region_configs(region_id)
    result = []
    for c in configs:
        result.append({"cpu": c["cpu"], "mem": c["mem"], "instance_type": c["instance_type"]})
    _instance_cache[region_id] = result
    return result


async def query_all_prices(region_id: str):
    configs = await _get_region_configs(region_id)
    if not configs:
        return []

    zone_id = await _get_zone_for_region(region_id)
    if zone_id == 0:
        return []

    cheap_groups = {}
    for c in configs:
        key = (c["cpu"], c["mem"])
        if key not in cheap_groups:
            cheap_groups[key] = c

    specs_to_query = list(cheap_groups.values())
    prices = await _query_prices_for_specs(region_id, zone_id, specs_to_query)

    results = []
    for c in cheap_groups.values():
        price = prices.get((c["cpu"], c["mem"]), 0)
        if price > 0:
            results.append({
                "provider": "腾讯云", "instance_type": c["instance_type"],
                "cpu": c["cpu"], "mem": c["mem"], "monthly_price": price,
                "currency": "CNY", "region_id": region_id,
            })
    return results


async def query_price(region_id: str, cpu: int, mem: int):
    configs = _instance_cache.get(region_id, [])
    if not configs:
        await get_instance_types(region_id)
        configs = _instance_cache.get(region_id, [])

    raw_configs = await _get_region_configs(region_id)
    matching = [c for c in raw_configs if c["cpu"] == cpu and c["mem"] == mem]
    if not matching:
        return {"provider": "腾讯云", "error": f"该地域无 {cpu}核{mem}G 的CDB规格"}

    zone_id = await _get_zone_for_region(region_id)
    if zone_id == 0:
        return {"provider": "腾讯云", "error": "无法获取可用区信息"}

    prices = await _query_prices_for_specs(region_id, zone_id, matching[:1])
    price = prices.get((cpu, mem), 0)

    if price > 0:
        return {
            "provider": "腾讯云",
            "instance_type": matching[0]["instance_type"],
            "cpu": cpu,
            "mem": mem,
            "monthly_price": price,
            "currency": "CNY",
            "region_id": region_id,
        }

    return {"provider": "腾讯云", "error": f"查询 {cpu}核{mem}G CDB价格失败"}
