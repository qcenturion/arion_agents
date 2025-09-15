import requests

def test_worldtime_api():
    url = "https://api.sunrise-sunset.org/json?lat=36.7201600&lng=-4.4203400"
    try:
        print(f"Requesting URL: {url}")
        r = requests.get(url, timeout=10)
        print(f"Status Code: {r.status_code}")
        r.raise_for_status()
        data = r.json()
        print("Response JSON:")
        print(data)
    except requests.exceptions.RequestException as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    test_worldtime_api()
