from fastapi.testclient import TestClient

import app


client = TestClient(app.app)


def test_home_planner_returns_budget_result():
    username = "smoketestuser"
    password = "pass123"

    reg = client.post(
        "/register",
        data={
            "username": username,
            "email": "smoketest@example.com",
            "password": password,
            "confirm_password": password,
        },
    )
    assert reg.status_code in (200, 303)

    login = client.post(
        "/login",
        data={"username": username, "password": password},
    )
    assert login.status_code in (200, 303)

    response = client.post(
        "/home-planner",
        data={
            "total_budget": "15000",
            "num_lights": "3",
            "num_fans": "2",
            "num_furniture": "1",
            "num_dining_tables": "1",
            "rooms": ["Living Room", "Kitchen"],
            "notes": "Need modern style",
        },
    )

    assert response.status_code == 200
    assert "Your Personalized Budget Plan" in response.text
    assert "budget_breakdown" not in response.text or "Lighting" in response.text
