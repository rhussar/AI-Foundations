from __future__ import annotations

import json
from pathlib import Path

import dash
import pandas as pd
import plotly.express as px
from dash import dcc, html

BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "lease_data.json"

app = dash.Dash(__name__, title="Black Ink | Property Portfolio")
server = app.server


def load_data() -> pd.DataFrame:
    if not DATA_PATH.exists():
        return pd.DataFrame()
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    properties = pd.DataFrame(payload.get("properties", []))
    if properties.empty:
        return properties
    properties["monthly_rent"] = pd.to_numeric(properties["monthly_rent"], errors="coerce")
    properties["annual_base_rent"] = pd.to_numeric(properties["annual_base_rent"], errors="coerce")
    properties["square_feet"] = pd.to_numeric(properties["square_feet"], errors="coerce")
    return properties


def money(value: float) -> str:
    return f"${value:,.0f}"


def metric(label: str, value: str, detail: str = "") -> html.Div:
    return html.Div(
        [html.Div(label, className="metric-label"), html.Div(value, className="metric-value"), html.Div(detail, className="metric-detail")],
        className="metric",
    )


def make_map(data: pd.DataFrame) -> dcc.Graph:
    if data.empty or not {"latitude", "longitude"}.issubset(data.columns):
        return html.Div("Run extract_leases.py to populate the property map.", className="empty-state")
    mapped = data.dropna(subset=["latitude", "longitude"]).copy()
    if mapped.empty:
        return html.Div("No geocoded properties found yet.", className="empty-state")
    figure = px.scatter_map(
        mapped,
        lat="latitude",
        lon="longitude",
        size="monthly_rent",
        size_max=42,
        color="monthly_rent",
        color_continuous_scale=[[0, "#f7a8c4"], [0.55, "#ff4f9a"], [1, "#ff0f78"]],
        hover_name="tenant",
        hover_data={"address": True, "monthly_rent": ":$,.0f", "latitude": False, "longitude": False},
        zoom=10,
        center={"lat": 41.34, "lon": -72.92},
        map_style="open-street-map",
    )
    figure.update_layout(
        paper_bgcolor="#111111",
        plot_bgcolor="#111111",
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        coloraxis_colorbar={"title": "Monthly rent", "tickprefix": "$", "tickformat": ",.0f"},
        font={"color": "#f7edf2", "family": "Space Grotesk"},
    )
    return dcc.Graph(figure=figure, config={"displayModeBar": False}, className="map-graph")


def layout() -> html.Div:
    data = load_data()
    total_monthly = data["monthly_rent"].sum() if not data.empty else 0
    total_annual = data["annual_base_rent"].sum() if not data.empty else 0
    total_sqft = data["square_feet"].sum() if not data.empty else 0
    rows = []
    if not data.empty:
        for _, row in data.sort_values("monthly_rent", ascending=False).iterrows():
            rows.append(
                html.Tr(
                    [
                        html.Td(row.get("tenant", "")),
                        html.Td(row.get("space_type", "")),
                        html.Td(row.get("address", "")),
                        html.Td(money(row.get("monthly_rent", 0))),
                        html.Td(money(row.get("annual_base_rent", 0))),
                    ]
                )
            )
    return html.Div(
        [
            html.Header([html.Div("BLACK / INK", className="wordmark"), html.Div("LEASE PORTFOLIO", className="header-tag")], className="topbar"),
            html.Main(
                [
                    html.Div([html.Div("PROPERTY DATA", className="eyebrow"), html.H1("Cash flow, mapped."), html.P("A living view of the lease portfolio."),], className="intro"),
                    html.Div(
                        [
                            metric("MONTHLY INCOME", money(total_monthly), "across all leases"),
                            metric("ANNUAL BASE RENT", money(total_annual), "contracted revenue"),
                            metric("LEASED AREA", f"{total_sqft:,.0f} sq ft", f"{len(data)} properties"),
                        ],
                        className="metrics",
                    ),
                    html.Section([html.Div([html.Div("01 / LOCATION", className="eyebrow"), html.H2("The portfolio, in place")], className="section-heading"), make_map(data)], className="map-section"),
                    html.Section([html.Div([html.Div("02 / LEDGER", className="eyebrow"), html.H2("Every lease at a glance")], className="section-heading"), html.Div(html.Table([html.Thead(html.Tr([html.Th("TENANT"), html.Th("TYPE"), html.Th("ADDRESS"), html.Th("MONTHLY"), html.Th("ANNUAL")])), html.Tbody(rows)]), className="table-wrap")], className="ledger-section"),
                ],
                className="page",
            ),
        ],
        className="app-shell",
    )


app.layout = layout

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=8050)
