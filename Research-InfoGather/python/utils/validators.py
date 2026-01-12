import requests

def validate_url(url, blacklist):
    # 1. Check Blacklist
    if any(domain in url for domain in blacklist):
        return json.dumps({"status": "REJECTED", "reason": "Domain is on the project blacklist."})
    
    # 2. Check if link is live
    try:
        response = requests.head(url, timeout=5)
        if response.status_code < 400:
            return json.dumps({"status": "VALID", "status_code": response.status_code})
        else:
            return json.dumps({"status": "BROKEN", "status_code": response.status_code})
    except Exception as e:
        return json.dumps({"status": "ERROR", "message": str(e)})