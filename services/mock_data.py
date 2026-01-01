"""Mock data for services"""
import random
from datetime import datetime, timedelta
from .models import Asset

# Generate mock assets
ASSET_TYPES = ["water_main", "sewer_line", "pump_station", "treatment_plant", "valve"]
CONDITIONS = ["excellent", "good", "fair", "poor", "critical"]
LOCATIONS = [f"District {i}" for i in range(1, 11)]

MOCK_ASSETS = []

# Generate 30 realistic assets
for i in range(1, 31):
    asset_type = random.choice(ASSET_TYPES)
    install_year = random.randint(1975, 2015)
    install_date = f"{install_year}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
    current_year = 2025
    current_age = current_year - install_year

    # Condition correlates with age
    if current_age < 10:
        condition = random.choice(["excellent", "good"])
    elif current_age < 20:
        condition = random.choice(["good", "fair"])
    elif current_age < 35:
        condition = random.choice(["fair", "poor"])
    else:
        condition = random.choice(["poor", "critical"])

    # Expected life based on asset type
    expected_life = {
        "water_main": 75,
        "sewer_line": 80,
        "pump_station": 40,
        "treatment_plant": 50,
        "valve": 50
    }[asset_type]

    # Replacement cost
    base_costs = {
        "water_main": 300000,
        "sewer_line": 350000,
        "pump_station": 800000,
        "treatment_plant": 2000000,
        "valve": 50000
    }
    replacement_cost = base_costs[asset_type] * random.uniform(0.8, 1.5)

    asset = Asset(
        id=f"asset-{i:03d}",
        name=f"{asset_type.replace('_', ' ').title()} - Section {i}",
        type=asset_type,
        install_date=install_date,
        location=random.choice(LOCATIONS),
        condition=condition,
        replacement_cost=round(replacement_cost, 2),
        expected_life_years=expected_life,
        current_age_years=current_age
    )
    MOCK_ASSETS.append(asset)


def get_assets_by_portfolio(portfolio_id: str = "default") -> list[Asset]:
    """Get all assets for a portfolio"""
    return MOCK_ASSETS


def get_asset_by_id(asset_id: str) -> Asset:
    """Get a single asset by ID"""
    for asset in MOCK_ASSETS:
        if asset.id == asset_id:
            return asset
    return None


def calculate_mock_risk(asset: Asset, horizon_months: int) -> dict:
    """Calculate mock risk scores for an asset"""
    # Simple risk model based on condition and age
    condition_scores = {
        "excellent": 0.05,
        "good": 0.15,
        "fair": 0.35,
        "poor": 0.65,
        "critical": 0.90
    }

    base_prob = condition_scores.get(asset.condition, 0.5)

    # Adjust for age vs expected life
    age_factor = asset.current_age_years / asset.expected_life_years
    if age_factor > 1.0:
        age_factor = 1.0 + (age_factor - 1.0) * 0.5  # Accelerate after expected life

    # Adjust for horizon
    horizon_factor = (horizon_months / 12) ** 0.5  # Square root for time adjustment

    probability = min(base_prob * age_factor * horizon_factor, 0.99)

    # Consequence based on replacement cost
    consequence = min(asset.replacement_cost / 500000 * 5, 10.0)

    risk_score = probability * consequence

    return {
        "probability_of_failure": round(probability, 4),
        "consequence_score": round(consequence, 2),
        "risk_score": round(risk_score, 2),
        "condition_assessment": asset.condition
    }


def optimize_mock_investments(candidates: list, budget: float, horizon_months: int) -> dict:
    """Simple greedy optimization - select highest ROI investments within budget"""
    # Calculate ROI for each candidate
    candidates_with_roi = []
    for c in candidates:
        roi = c.expected_risk_reduction / c.cost if c.cost > 0 else 0
        candidates_with_roi.append({
            "candidate": c,
            "roi": roi
        })

    # Sort by ROI descending
    candidates_with_roi.sort(key=lambda x: x["roi"], reverse=True)

    # Greedy selection
    selected = []
    budget_used = 0
    total_risk_reduction = 0
    rank = 1

    for item in candidates_with_roi:
        c = item["candidate"]
        if budget_used + c.cost <= budget:
            selected.append({
                "asset_id": c.asset_id,
                "intervention_type": c.intervention_type,
                "cost": c.cost,
                "expected_risk_reduction": c.expected_risk_reduction,
                "priority_rank": rank
            })
            budget_used += c.cost
            total_risk_reduction += c.expected_risk_reduction
            rank += 1

    return {
        "selected_investments": selected,
        "budget_used": round(budget_used, 2),
        "budget_remaining": round(budget - budget_used, 2),
        "total_risk_reduction": round(total_risk_reduction, 4)
    }
