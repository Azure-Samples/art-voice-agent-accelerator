#!/usr/bin/env python3
"""
Simple test script for Card Decline API
"""
import sys
import json
import httpx

BASE_URL = "http://localhost:8000"

def test_health():
    """Test health endpoint"""
    print("Testing health endpoint...")
    response = httpx.get(f"{BASE_URL}/health")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}\n")
    return response.status_code == 200

def test_get_code():
    """Test getting a specific code"""
    print("Testing GET /api/v1/codes/51...")
    response = httpx.get(f"{BASE_URL}/api/v1/codes/51")
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Code: {data['code']}")
    print(f"Description: {data['description']}")
    print(f"Actions: {', '.join(data['actions'])}\n")
    return response.status_code == 200

def test_search():
    """Test search endpoint"""
    print("Testing search for 'insufficient'...")
    response = httpx.get(f"{BASE_URL}/api/v1/search", params={"q": "insufficient"})
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Found {data['total']} codes")
    if data['codes']:
        print(f"First result: {data['codes'][0]['code']} - {data['codes'][0]['description']}\n")
    return response.status_code == 200

def test_get_all():
    """Test getting all codes"""
    print("Testing GET all numeric codes...")
    response = httpx.get(f"{BASE_URL}/api/v1/codes", params={"code_type": "numeric"})
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Total numeric codes: {data['total']}\n")
    return response.status_code == 200

def test_metadata():
    """Test metadata endpoint"""
    print("Testing metadata endpoint...")
    response = httpx.get(f"{BASE_URL}/api/v1/metadata")
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Numeric codes: {data['numeric_codes_count']}")
    print(f"Alphanumeric codes: {data['alphanumeric_codes_count']}\n")
    return response.status_code == 200

def main():
    """Run all tests"""
    print("=" * 60)
    print("Card Decline API Test Suite")
    print("=" * 60 + "\n")
    
    tests = [
        test_health,
        test_get_code,
        test_search,
        test_get_all,
        test_metadata
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"ERROR: {e}\n")
            results.append(False)
    
    print("=" * 60)
    print(f"Results: {sum(results)}/{len(results)} tests passed")
    print("=" * 60)
    
    return 0 if all(results) else 1

if __name__ == "__main__":
    sys.exit(main())
