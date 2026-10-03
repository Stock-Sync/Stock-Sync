"""
Rotas de API para Métricas de Vendas do sales-service.

Endpoints:
  - GET /api/v1/metrics - Métricas agregadas com filtros
"""

import logging
from typing import Optional
from uuid import UUID
from datetime import date, datetime

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select, func, case

from app.db.session import get_session
from app.models.sale_metric import SaleMetric

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("")
def get_metrics(
    session: Session = Depends(get_session),
    user_id: Optional[UUID] = Query(None, description="Filtrar por tenant"),
    marketplace: Optional[str] = Query(None, description="Filtrar por marketplace (mercadolivre, shopee)"),
    sku: Optional[str] = Query(None, description="Filtrar por SKU"),
    metric_type: Optional[str] = Query(None, description="Filtrar por tipo (total_revenue, total_orders, total_items_sold, sku_revenue, sku_orders, sku_items_sold)"),
    start_date: Optional[date] = Query(None, description="Data início (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="Data fim (YYYY-MM-DD)"),
    group_by: Optional[str] = Query(None, description="Agrupar por: day, week, month, marketplace, sku"),
    limit: int = Query(1000, ge=1, le=10000, description="Limite de resultados"),
    offset: int = Query(0, ge=0, description="Offset para paginação"),
):
    """
    Retorna métricas agregadas de vendas com filtros.

    Filtros:
    - user_id: UUID do tenant
    - marketplace: mercadolivre ou shopee
    - sku: SKU específico (para métricas por SKU)
    - metric_type: total_revenue, total_orders, total_items_sold, sku_revenue, sku_orders, sku_items_sold
    - start_date/end_date: Intervalo de datas
    - group_by: day, week, month, marketplace, sku (agrupa resultados)

    Exemplos:
    - /api/v1/metrics?marketplace=mercadolivre&start_date=2026-01-01&end_date=2026-01-31
    - /api/v1/metrics?metric_type=total_revenue&group_by=week
    - /api/v1/metrics?sku=SKU-123&metric_type=sku_revenue
    """
    query = select(SaleMetric)

    # Filtros
    if user_id:
        query = query.where(SaleMetric.user_id == user_id)
    if marketplace:
        query = query.where(SaleMetric.marketplace == marketplace)
    if sku:
        query = query.where(SaleMetric.sku == sku)
    if metric_type:
        query = query.where(SaleMetric.metric_type == metric_type)
    if start_date:
        query = query.where(SaleMetric.metric_date >= start_date)
    if end_date:
        query = query.where(SaleMetric.metric_date <= end_date)

    # Agrupamento
    if group_by:
        if group_by == "day":
            query = query.group_by(SaleMetric.metric_date, SaleMetric.marketplace, SaleMetric.metric_type, SaleMetric.user_id, SaleMetric.sku)
        elif group_by == "week":
            query = query.group_by(func.date_trunc('week', SaleMetric.metric_date), SaleMetric.marketplace, SaleMetric.metric_type, SaleMetric.user_id, SaleMetric.sku)
        elif group_by == "month":
            query = query.group_by(func.date_trunc('month', SaleMetric.metric_date), SaleMetric.marketplace, SaleMetric.metric_type, SaleMetric.user_id, SaleMetric.sku)
        elif group_by == "marketplace":
            query = query.group_by(SaleMetric.marketplace)
        elif group_by == "sku":
            query = query.group_by(SaleMetric.sku)
        else:
            query = query.group_by(SaleMetric.metric_date, SaleMetric.marketplace, SaleMetric.metric_type, SaleMetric.user_id, SaleMetric.sku)

        # Soma os valores agrupados
        query = query.with_only_columns(
            func.sum(SaleMetric.value).label("value"),
            SaleMetric.metric_date,
            SaleMetric.marketplace,
            SaleMetric.metric_type,
            SaleMetric.user_id,
            SaleMetric.sku,
        )
    else:
        # Sem agrupamento, retorna linhas individuais
        pass

    query = query.order_by(SaleMetric.metric_date.desc()).offset(offset).limit(limit)
    results = session.exec(query).all()

    # Formata resposta
    if group_by:
        return [
            {
                "value": float(r[0]) if r[0] else 0,
                "metric_date": r[1].isoformat() if r[1] else None,
                "marketplace": r[2],
                "metric_type": r[3],
                "user_id": str(r[4]),
                "sku": r[5],
            }
            for r in results
        ]
    else:
        return [
            {
                "id": str(r.id),
                "user_id": str(r.user_id),
                "sku": r.sku,
                "metric_date": r.metric_date.isoformat(),
                "marketplace": r.marketplace,
                "metric_type": r.metric_type,
                "value": float(r.value),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in results
        ]


@router.get("/summary")
def get_metrics_summary(
    session: Session = Depends(get_session),
    user_id: Optional[UUID] = Query(None, description="Filtrar por tenant"),
    marketplace: Optional[str] = Query(None, description="Filtrar por marketplace"),
    start_date: Optional[date] = Query(None, description="Data início (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="Data fim (YYYY-MM-DD)"),
):
    """
    Retorna resumo consolidado das principais métricas.
    Útil para dashboard - uma única chamada retorna tudo.
    """
    # Query base
    base_query = select(SaleMetric)
    if user_id:
        base_query = base_query.where(SaleMetric.user_id == user_id)
    if marketplace:
        base_query = base_query.where(SaleMetric.marketplace == marketplace)
    if start_date:
        base_query = base_query.where(SaleMetric.metric_date >= start_date)
    if end_date:
        base_query = base_query.where(SaleMetric.metric_date <= end_date)

    # Métricas globais (sku IS NULL)
    global_query = base_query.where(SaleMetric.sku.is_(None))

    # Agrega por metric_type
    revenue = session.exec(
        global_query.where(SaleMetric.metric_type == "total_revenue")
        .with_only_columns(func.sum(SaleMetric.value))
    ).first() or 0

    orders = session.exec(
        global_query.where(SaleMetric.metric_type == "total_orders")
        .with_only_columns(func.sum(SaleMetric.value))
    ).first() or 0

    items = session.exec(
        global_query.where(SaleMetric.metric_type == "total_items_sold")
        .with_only_columns(func.sum(SaleMetric.value))
    ).first() or 0

    # Top SKUs por receita
    top_skus = session.exec(
        base_query.where(SaleMetric.metric_type == "sku_revenue")
        .where(SaleMetric.sku.is_not(None))
        .group_by(SaleMetric.sku, SaleMetric.marketplace)
        .with_only_columns(
            SaleMetric.sku,
            SaleMetric.marketplace,
            func.sum(SaleMetric.value).label("total_revenue")
        )
        .order_by(func.sum(SaleMetric.value).desc())
        .limit(10)
    ).all()

    return {
        "total_revenue": float(revenue),
        "total_orders": int(orders),
        "total_items_sold": int(items),
        "avg_order_value": float(revenue) / int(orders) if int(orders) > 0 else 0,
        "top_skus": [
            {"sku": r[0], "marketplace": r[1], "revenue": float(r[2])}
            for r in top_skus
        ],
        "period": {
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
        }
    }