import pytest
import httpx
import asyncio
import os

CORE_URL = os.getenv("CORE_SERVICE_URL", "http://localhost:8001")
DASHBOARD_URL = os.getenv("DASHBOARD_SERVICE_URL", "http://localhost:8003")

@pytest.mark.asyncio
async def test_end_to_end_payment_flow():
    async with httpx.AsyncClient() as client:
        # 1. Create a Merchant
        import time
        unique_suffix = int(time.time())
        res = await client.post(f"{CORE_URL}/api/merchants", json={
            "name": f"Test Merchant E2E {unique_suffix}",
            "email": f"test-e2e-{unique_suffix}@example.com"
        })
        assert res.status_code == 201, f"Failed to create merchant: {res.text}"
        merchant = res.json()
        merchant_id = merchant["merchant_id"]
        api_key = merchant["api_key"]
        headers = {"X-API-Key": str(api_key)}
        
        # 2. Create a Customer for this merchant
        res = await client.post(f"{CORE_URL}/api/{merchant_id}/customers", json={
            "name": "John Doe",
            "email": "john.doe@example.com",
            "phone": "+1234567890"
        }, headers=headers)
        assert res.status_code == 201, f"Failed to create customer: {res.text}"
        customer = res.json()
        customer_id = customer["customer_id"]
        
        # 3. Create a Payment
        res = await client.post(f"{CORE_URL}/api/{merchant_id}/payments", json={
            "customer_id": customer_id,
            "amount": 150.50,
            "currency": "USD",
            "method": "card",
            "description": "Test E2E Payment"
        }, headers=headers)
        assert res.status_code == 201, f"Failed to create payment: {res.text}"
        payment = res.json()
        payment_id = payment["payment_id"]
        
        # 4. Authorize and Capture Payment
        res = await client.post(f"{CORE_URL}/api/{merchant_id}/payments/{payment_id}/authorize", headers=headers)
        assert res.status_code == 200, f"Failed to authorize payment: {res.text}"
        
        res = await client.post(f"{CORE_URL}/api/{merchant_id}/payments/{payment_id}/capture", headers=headers)
        assert res.status_code == 200, f"Failed to capture payment: {res.text}"
        assert res.json()["status"] == "captured"
        
        # 5. Wait for events to sync to read-db via Connect Service
        # Add retry logic since Kafka sync might take longer depending on load
        max_retries = 10
        payments = []
        for i in range(max_retries):
            await asyncio.sleep(2)
            res = await client.get(f"{DASHBOARD_URL}/api/{merchant_id}/payments?limit=10&offset=0", headers=headers)
            if res.status_code == 200:
                body = res.json()
                items = body.get("items", []) if isinstance(body, dict) else body
                # The dashboard response structure for list payments is {"data": [...], "total": ...}
                if isinstance(body, dict) and "data" in body:
                    items = body["data"]
                
                synced = next((p for p in items if p["payment_id"] == payment_id), None)
                if synced and synced["status"] == "captured":
                    payments = items
                    break
        else:
            assert False, "Timeout waiting for payment to sync and reach 'captured' status in dashboard"
        assert len(payments) > 0, "No payments synced to dashboard"
        
        synced_payment = next((p for p in payments if p["payment_id"] == payment_id), None)
        assert synced_payment is not None, "Synced payment not found"
        assert synced_payment["status"] == "captured"
        assert float(synced_payment["amount"]) == 150.50  # Should be preserved properly

        # 7. Create a Refund
        res = await client.post(f"{CORE_URL}/api/{merchant_id}/payments/{payment_id}/refund", json={
            "amount": 50.00,
            "reason": "Partial E2E Refund"
        }, headers=headers)
        assert res.status_code == 201, f"Failed to create refund: {res.text}"
        refund = res.json()
        
        # 8. Check events API for pagination and functionality
        res = await client.get(f"{CORE_URL}/api/events?limit=5")
        assert res.status_code == 200
        events = res.json()
        assert isinstance(events, list)
        
        print("E2E Test Passed Successfully!")
