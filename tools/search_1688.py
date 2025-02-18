from crewai.tools import BaseTool, tool
from typing import Type
from pydantic import BaseModel, Field
import requests
import os
import json
import hashlib
import logging

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Set API_MODE to either "online" or "mocked_data" (default: online)
API_MODE = os.getenv("API_MODE", "online").lower()
CACHE_DIR = "api_cache"

if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

@tool("search1688")
def search1688(query: str,
               page: int = 1,
               page_size: int = 20,
               sort: str = "sales") -> dict:
    """Search items on 1688.com using the API.

    Args:
        query (str): Search keyword.
        page (int): Page number (default: 1).
        page_size (int): Number of items per page (default: 20).
        sort (str): Sorting method (default: "sales").

    Returns:
        dict: List of items with their details."""
    base_url = "http://api.tmapi.top/1688"
    api_token = os.environ.get("TMAPI_TOKEN")

    endpoint = f"{base_url}/search/items"
    params = {
        "page": page,
        "page_size": page_size,
        "keyword": query,
        "sort": sort,
        "apiToken": api_token
    }

    # Create a unique key for caching based on the search parameters
    key = hashlib.md5(
        f"{query}_{page}_{page_size}_{sort}".encode("utf-8")).hexdigest()
    cache_file = os.path.join(CACHE_DIR, f"search_{key}.json")

    logger.debug(f"Search request - Mode: {API_MODE}, Query: {query}, Cache file: {cache_file}")

    if API_MODE == "mocked_data":
        logger.info("Using mocked data mode")
        try:
            with open(cache_file, "r") as f:
                data = json.load(f)
                logger.debug("Successfully loaded mock data from cache")
        except Exception as e:
            logger.warning(f"Failed to load mock data: {str(e)}")
            return {"items": [], "error": "No cached data available"}
    else:
        logger.info("Using online mode - making API request")
        if not api_token:
            logger.error("API token not found")
            return {"items": [], "error": "API token not configured"}

        try:
            response = requests.get(endpoint, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            logger.debug("Successfully received API response")

            # Cache the response
            try:
                with open(cache_file, "w") as f:
                    json.dump(data, f)
                logger.debug("Successfully cached API response")
            except Exception as e:
                logger.warning(f"Failed to save search cache: {str(e)}")
        except Exception as e:
            logger.error(f"API request failed: {str(e)}")
            return {"items": [], "error": str(e)}

    if data.get("code") == 200:
        items = []
        for item in data.get("data", {}).get("items", []):
            formatted_item = {
                "title": item.get("title", ""),
                "item_id": item.get("item_id", ""),
                "product_url": item.get("product_url", ""),
                "item_score": str(item.get("goods_score", "No data available")),
                "repurchase_rate": str(item.get("item_repurchase_rate", "No data available")),
                "orders_count": str(item.get("sale_info", {}).get("orders_count", 0)),
                "price": item.get("price", ""),
            }
            items.append(formatted_item)
        logger.info(f"Successfully processed {len(items)} items")
        return {"items": items}
    else:
        error_msg = data.get("msg", "Unknown error")
        logger.error(f"API Error: {error_msg}")
        return {"items": [], "error": error_msg}


@tool("item_detail")
def item_detail(item_id: str) -> dict:
    """Get detailed information about an item on 1688.com using its item_id.

    Args:
        item_id (int): The unique identifier of the item.

    Returns:
        dict: Detailed item information if successful; otherwise, an empty dictionary.
    """
    base_url = "http://api.tmapi.top/1688"
    api_token = os.environ.get("TMAPI_TOKEN")

    endpoint = f"{base_url}/v2/item_detail"
    params = {
        "item_id": item_id,
        "apiToken": api_token,
    }

    cache_file = os.path.join(CACHE_DIR, f"item_detail_{item_id}.json")

    logger.debug(f"Detail request - Mode: {API_MODE}, Item ID: {item_id}, Cache file: {cache_file}")

    if API_MODE == "mocked_data":
        logger.info("Using mocked data mode for item detail")
        try:
            with open(cache_file, "r") as f:
                data = json.load(f)
                logger.debug("Successfully loaded mock item detail from cache")
        except Exception as e:
            logger.warning(f"Failed to load mock item detail: {str(e)}")
            return {}
    else:
        logger.info("Using online mode - making API request for item detail")
        if not api_token:
            logger.error("API token not found")
            return {}

        try:
            response = requests.get(endpoint, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            logger.debug("Successfully received item detail API response")

            # Cache the response
            try:
                with open(cache_file, "w") as f:
                    json.dump(data, f)
                logger.debug("Successfully cached item detail response")
            except Exception as e:
                logger.warning(f"Failed to save item detail cache: {str(e)}")
        except Exception as e:
            logger.error(f"Item detail API request failed: {str(e)}")
            return {}

    if data.get("code") == 200:
        logger.info("Successfully retrieved item details")
        return data.get("data", {})
    else:
        error_msg = data.get("msg", "Unknown error")
        logger.error(f"Item detail API Error: {error_msg}")
        return {}