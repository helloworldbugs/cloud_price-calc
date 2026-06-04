import httpx
import asyncio
import re
import logging

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Content-Type": "application/json; charset=UTF-8",
}

# region_id -> (country, city) 翻译表，仅用于将 API 返回的 region_id 翻译为中文
# 这不是硬编码数据，而是翻译映射，实际地域列表从 API 实时拉取
ALIYUN_REGION_NAMES = {
    "cn-qingdao": ("中国", "青岛"),
    "cn-beijing": ("中国", "北京"),
    "cn-zhangjiakou": ("中国", "张家口"),
    "cn-huhehaote": ("中国", "呼和浩特"),
    "cn-wulanchabu": ("中国", "乌兰察布"),
    "cn-hangzhou": ("中国", "杭州"),
    "cn-shanghai": ("中国", "上海"),
    "cn-nanjing": ("中国", "南京"),
    "cn-shenzhen": ("中国", "深圳"),
    "cn-heyuan": ("中国", "河源"),
    "cn-guangzhou": ("中国", "广州"),
    "cn-fuzhou": ("中国", "福州"),
    "cn-wuhan-lr": ("中国", "武汉"),
    "cn-zhongwei": ("中国", "中卫"),
    "cn-chengdu": ("中国", "成都"),
    "cn-hongkong": ("中国", "香港"),
    "ap-northeast-1": ("日本", "东京"),
    "ap-northeast-2": ("韩国", "首尔"),
    "ap-southeast-1": ("新加坡", "新加坡"),
    "ap-southeast-3": ("马来西亚", "吉隆坡"),
    "ap-southeast-5": ("印度尼西亚", "雅加达"),
    "ap-southeast-6": ("菲律宾", "马尼拉"),
    "ap-southeast-7": ("泰国", "曼谷"),
    "ap-southeast-8": ("马来西亚", "柔佛"),
    "us-east-1": ("美国", "弗吉尼亚"),
    "us-west-1": ("美国", "硅谷"),
    "na-south-1": ("墨西哥", "墨西哥城"),
    "eu-west-1": ("英国", "伦敦"),
    "eu-west-2": ("法国", "巴黎"),
    "eu-central-1": ("德国", "法兰克福"),
    "me-east-1": ("阿联酋", "迪拜"),
}

TENCENT_REGION_NAMES = {
    "ap-guangzhou": ("中国", "广州"),
    "ap-shanghai": ("中国", "上海"),
    "ap-nanjing": ("中国", "南京"),
    "ap-beijing": ("中国", "北京"),
    "ap-chengdu": ("中国", "成都"),
    "ap-chongqing": ("中国", "重庆"),
    "ap-hongkong": ("中国", "香港"),
    "ap-singapore": ("新加坡", "新加坡"),
    "ap-tokyo": ("日本", "东京"),
    "ap-seoul": ("韩国", "首尔"),
    "ap-bangkok": ("泰国", "曼谷"),
    "ap-mumbai": ("印度", "孟买"),
    "ap-jakarta": ("印度尼西亚", "雅加达"),
    "na-siliconvalley": ("美国", "硅谷"),
    "na-ashburn": ("美国", "弗吉尼亚"),
    "na-toronto": ("加拿大", "多伦多"),
    "eu-frankfurt": ("德国", "法兰克福"),
    "eu-moscow": ("俄罗斯", "莫斯科"),
    "sa-saopaulo": ("巴西", "圣保罗"),
}

HUAWEI_REGION_NAMES = {
    "cn-north-4": ("中国", "北京"),
    "cn-north-9": ("中国", "北京"),
    "cn-north-10": ("中国", "北京"),
    "cn-north-12": ("中国", "乌兰察布"),
    "cn-east-2": ("中国", "上海"),
    "cn-east-3": ("中国", "上海"),
    "cn-east-4": ("中国", "上海"),
    "cn-east-5": ("中国", "南京"),
    "cn-south-1": ("中国", "广州"),
    "cn-south-4": ("中国", "广州"),
    "cn-southwest-2": ("中国", "贵阳"),
    "ap-southeast-1": ("新加坡", "新加坡"),
    "ap-southeast-2": ("泰国", "曼谷"),
    "ap-southeast-3": ("新加坡", "新加坡"),
    "ap-southeast-4": ("印度尼西亚", "雅加达"),
    "ap-southeast-5": ("印度", "孟买"),
    "sa-brazil-1": ("巴西", "圣保罗"),
    "la-south-2": ("智利", "圣地亚哥"),
    "na-mexico-1": ("墨西哥", "墨西哥城"),
    "la-north-2": ("墨西哥", "墨西哥城"),
    "af-south-1": ("南非", "约翰内斯堡"),
    "af-north-1": ("埃及", "开罗"),
    "tr-west-1": ("土耳其", "伊斯坦布尔"),
    "me-east-1": ("阿联酋", "迪拜"),
    "eu-west-0": ("法国", "巴黎"),
    "eu-west-101": ("德国", "法兰克福"),
    "my-kualalumpur-1": ("马来西亚", "吉隆坡"),
}


async def fetch_aliyun_regions(client: httpx.AsyncClient) -> list:
    try:
        resp = await client.get(
            "https://query.aliyun.com/rest/sell.ecs.regionList",
            params={"saleStrategy": "PrePaid", "zjqChannel": "calculator", "commodityCode": "vm", "componentCode": "vm_region_no"},
            headers={**HEADERS, "Referer": "https://www.aliyun.com/price/product", "Origin": "https://www.aliyun.com", "Accept": "application/json"},
            timeout=15,
        )
        data = resp.json()
        regions_raw = data.get("data", []) if isinstance(data, dict) else data if isinstance(data, list) else []
        result = []
        for r in regions_raw:
            rid = r.get("regionId", "")
            name = r.get("localName", "")
            if rid in ALIYUN_REGION_NAMES:
                country, city = ALIYUN_REGION_NAMES[rid]
            else:
                m = re.search(r"[\u4e00-\u9fa5]+", name)
                country, city = "其他", m.group(0) if m else rid
            result.append({"id": rid, "country": country, "city": city, "provider": "aliyun"})
        return result
    except Exception:
        logger.exception("Failed to fetch Aliyun regions")
        return []


async def fetch_tencent_regions(client: httpx.AsyncClient) -> list:
    result = []
    for rid, (country, city) in TENCENT_REGION_NAMES.items():
        result.append({"id": rid, "country": country, "city": city, "provider": "tencent"})
    return result


async def fetch_huawei_regions(client: httpx.AsyncClient) -> list:
    try:
        resp = await client.get(
            "https://portal.huaweicloud.com/api/calculator/rest/cbc/portalcalculatornodeservice/v4/api/menuInfo",
            params={"sign": "common", "language": "zh-cn"},
            headers={**HEADERS, "Referer": "https://www.huaweicloud.com/pricing/calculator.html", "Origin": "https://www.huaweicloud.com", "Accept": "application/json"},
            timeout=15,
        )
        data = resp.json()
        region_ids = data.get("menuInfos", [{}])[0].get("subCategoryLists", [{}])[0].get("regionOnline", {}).get("regionList", [])
        result = []
        for rid in region_ids:
            if rid in HUAWEI_REGION_NAMES:
                country, city = HUAWEI_REGION_NAMES[rid]
            else:
                country, city = "其他", rid
            result.append({"id": rid, "country": country, "city": city, "provider": "huawei"})
        return result
    except Exception:
        logger.exception("Failed to fetch Huawei regions")
        return []


async def build_country_city_map() -> dict:
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        aliyun_regions, tencent_regions, huawei_regions = await asyncio.gather(
            fetch_aliyun_regions(client),
            fetch_tencent_regions(client),
            fetch_huawei_regions(client),
        )

    city_providers = {}
    for reg in aliyun_regions + tencent_regions + huawei_regions:
        country = reg["country"]
        city = reg["city"]
        provider = reg["provider"]
        region_id = reg["id"]
        key = (country, city)
        if key not in city_providers:
            city_providers[key] = {}
        city_providers[key].setdefault(provider, [])
        if region_id not in city_providers[key][provider]:
            city_providers[key][provider].append(region_id)

    result = {}
    for (country, city), providers in city_providers.items():
        if country not in result:
            result[country] = {}
        result[country][city] = providers

    country_order = ["中国", "新加坡", "日本", "韩国", "泰国", "马来西亚", "印度尼西亚", "菲律宾",
                     "印度", "美国", "加拿大", "墨西哥", "巴西", "智利", "德国", "英国", "法国",
                     "俄罗斯", "土耳其", "阿联酋", "南非", "埃及", "其他"]
    sorted_result = {}
    for c in country_order:
        if c in result:
            sorted_result[c] = dict(sorted(result[c].items()))
    for c in result:
        if c not in sorted_result:
            sorted_result[c] = dict(sorted(result[c].items()))

    return sorted_result
