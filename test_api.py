#!/usr/bin/env python3
# ============================================================
# test_api.py  –  API Client Test
# Tests the Color Analyzer API against a real webpage
# Usage: python3 test_api.py
# ============================================================

import requests
import json
import sys
from urllib.parse import quote

# Configuration
API_BASE_URL = "https://contraste-zpkl.onrender.com"
TEST_URL = "https://vimochini.github.io/Mini-Projects/Electro%20dash.html"

def test_health():
    """Test /health endpoint."""
    print("\n" + "="*60)
    print("TEST 1: Health Check")
    print("="*60)
    try:
        resp = requests.get(f"{API_BASE_URL}/health", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        print(f"✓ Status: {resp.status_code}")
        print(f"✓ Response: {json.dumps(data, indent=2)}")
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_home():
    """Test GET / endpoint."""
    print("\n" + "="*60)
    print("TEST 2: Home Endpoint")
    print("="*60)
    try:
        resp = requests.get(f"{API_BASE_URL}/", timeout=10)
        resp.raise_for_status()
        data = resp.json()
        print(f"✓ Status: {resp.status_code}")
        print(f"✓ API Version: {data.get('version')}")
        print(f"✓ Endpoints available:")
        for endpoint, desc in data.get("endpoints", {}).items():
            print(f"  - {endpoint}: {desc}")
        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_analyze(url):
    """Test POST /analyze endpoint with real webpage."""
    print("\n" + "="*60)
    print(f"TEST 3: Full Analysis")
    print(f"URL: {url}")
    print("="*60)
    try:
        payload = {"url": url}
        resp = requests.post(
            f"{API_BASE_URL}/analyze",
            json=payload,
            timeout=30
        )
        resp.raise_for_status()
        data = resp.json()

        print(f"✓ Status: {resp.status_code}")
        print(f"✓ Request ID: {data.get('request_id')}")
        print(f"✓ Cached: {data.get('cached')}")
        print(f"✓ Colors Found: {data.get('total_colors_found')}")

        colors = data.get("extracted_colors", [])
        print(f"✓ Color Palette: {colors[:5]}{'...' if len(colors) > 5 else ''}")

        scheme = data.get("color_scheme", {})
        print(f"✓ Color Scheme: {scheme.get('name')} ({scheme.get('type')})")

        accessibility = data.get("accessibility", {})
        print(f"✓ Accessibility Score: {accessibility.get('accessibility_score')}%")
        print(f"✓ Score Label: {accessibility.get('score_label')}")
        print(f"✓ AA Passing Pairs: {accessibility.get('aa_passing_pairs')} / {accessibility.get('total_pairs')}")

        return True
    except requests.exceptions.Timeout:
        print(f"✗ Request timed out (30s) — page may be slow or inaccessible")
        return False
    except requests.exceptions.HTTPError as e:
        print(f"✗ HTTP {e.response.status_code}: {e.response.text}")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_accessibility_endpoint():
    """Test POST /accessibility endpoint with sample colors."""
    print("\n" + "="*60)
    print("TEST 4: Accessibility Check (Sample Colors)")
    print("="*60)
    try:
        payload = {
            "colors": ["#FF5733", "#FFFFFF", "#333333", "#1E90FF"]
        }
        resp = requests.post(
            f"{API_BASE_URL}/accessibility",
            json=payload,
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()

        print(f"✓ Status: {resp.status_code}")
        print(f"✓ Colors Checked: {data.get('colors_checked')}")

        accessibility = data.get("accessibility", {})
        print(f"✓ Accessibility Score: {accessibility.get('accessibility_score')}%")
        print(f"✓ AA Passing Pairs: {accessibility.get('aa_passing_pairs')} / {accessibility.get('total_pairs')}")

        suggestions = data.get("suggestions", [])
        print(f"✓ Color Suggestions: {len(suggestions)} recommendations")

        return True
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def main():
    """Run all tests."""
    print("\n")
    print("╔" + "="*58 + "╗")
    print("║  Color Analyzer API - Test Suite                          ║")
    print("║  Base URL: " + API_BASE_URL.ljust(46) + "║")
    print("╚" + "="*58 + "╝")

    results = []

    # Run tests
    results.append(("Health Check", test_health()))
    results.append(("Home Endpoint", test_home()))
    results.append(("Full Analysis", test_analyze(TEST_URL)))
    results.append(("Accessibility Endpoint", test_accessibility_endpoint()))

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status:8} {test_name}")

    print("="*60)
    print(f"Result: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! API is working correctly.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Check errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
