from crewai.tools import BaseTool
from typing import Type
from pydantic import BaseModel, Field
import requests
import os
import json
import hashlib

# Set API_MODE to either "online" or "mocked_data" (default: online)
API_MODE = os.getenv("API_MODE", "online").lower()
CACHE_DIR = "api_cache"

if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)


class MyCustomToolInput(BaseModel):
    """Input schema for MyCustomTool."""
    argument: str = Field(..., description="Description of the argument.")


class MyCustomTool(BaseTool):
    name: str = "Name of my tool"
    description: str = (
        "Clear description for what this tool is useful for, your agent will need this information to use it."
    )
    args_schema: Type[BaseModel] = MyCustomToolInput

    def _run(self, argument: str) -> str:
        # Implementation goes here
        return "this is an example of a tool output, ignore it and move along."


from crewai.tools import tool


@tool("search1688")
def search1688(query: str,
               page: int = 1,
               page_size: int = 20,
               sort: str = "sales") -> str:
    """Search items on 1688.com using the API.
        
        Args:
            query (str): Search keyword.
            page (int): Page number (default: 1).
            page_size (int): Number of items per page (default: 20).
            sort (str): Sorting method (default: "sales").
            
        Returns:
            List[Dict]: List of items with their details."""
    base_url = "http://api.tmapi.top/1688"
    api_token = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJVc2VybmFtZSI6ImlsZ2l6IiwiQ29taWQiOm51bGwsIlJvbGVpZCI6bnVsbCwiaXNzIjoidG1hcGkiLCJzdWIiOiJpbGdpeiIsImF1ZCI6WyIiXSwiaWF0IjoxNzM4NzYzMTg1fQ.tTzyOqooykFSJcw8ZOQ0sGkGki7BTRluiV7YT-e8HIc"
    )

    endpoint = f"{base_url}/search/items"
    params = {
        "page": page,
        "page_size": page_size,
        "keyword": query,
        "sort": sort,
        "apiToken": api_token
    }

    # Create a unique key for caching based on the search parameters.
    key = hashlib.md5(
        f"{query}_{page}_{page_size}_{sort}".encode("utf-8")).hexdigest()
    cache_file = os.path.join(CACHE_DIR, f"search_{key}.json")

    if API_MODE == "mocked_data":
        try:
            with open(cache_file, "r") as f:
                data = json.load(f)
        except Exception as e:
            # Cache not found; return an empty list.
            return []
    else:
        response = requests.get(endpoint, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        try:
            with open(cache_file, "w") as f:
                json.dump(data, f)
        except Exception as e:
            print("Warning: failed to save search cache:", e)

    if data["code"] == 200:
        items = []
        for item in data["data"]["items"]:
            formatted_item = {
                "name_cn": item.get("title", ""),
                "item_id": item.get("item_id", ""),
                "url": item.get("product_url", ""),
                "price": item.get("price", "")
            }
            items.append(formatted_item)

        return items
    else:
        error_msg = f"API Error: {data.get('msg', 'Unknown error')}"
        return []


# ---------------------------
# New Tool: Retrieve Item Details
# ---------------------------
@tool("item_detail")
def item_detail(item_id: int) -> dict:
    """
    Get detailed information about an item on 1688.com using its item_id.
    
    Args:
        item_id (int): The unique identifier of the item.
    
    Returns:
        Dict: Detailed item information if the API call is successful; otherwise, an empty dictionary.
    """
    base_url = "http://api.tmapi.top/1688"
    api_token = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJVc2VybmFtZSI6ImlsZ2l6IiwiQ29taWQiOm51bGwsIlJvbGVpZCI6bnVsbCwiaXNzIjoidG1hcGkiLCJzdWIiOiJpbGdpeiIsImF1ZCI6WyIiXSwiaWF0IjoxNzM4NzYzMTg1fQ.tTzyOqooykFSJcw8ZOQ0sGkGki7BTRluiV7YT-e8HIc"
    )

    endpoint = f"{base_url}/v2/item_detail"
    params = {
        "item_id": item_id,
        "apiToken": api_token,
    }

    cache_file = os.path.join(CACHE_DIR, f"item_detail_{item_id}.json")

    if API_MODE == "mocked_data":
        try:
            with open(cache_file, "r") as f:
                data = json.load(f)
        except Exception as e:
            return {}
    else:
        response = requests.get(endpoint, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        try:
            with open(cache_file, "w") as f:
                json.dump(data, f)
        except Exception as e:
            print("Warning: failed to save item_detail cache:", e)

    if data.get("code") == 200:
        return data.get("data", {})
    else:
        # If API response indicates an error, return an empty dictionary.
        return {}
