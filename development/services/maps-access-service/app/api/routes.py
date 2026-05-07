"""
Maps Access Service — API Route Handlers.

Exposes geocoding endpoints for BL services. No authentication —
this is an access-layer service blocked from external access by
the absence of an NGINX upstream (same pattern as DB-access services).
"""

from fastapi import APIRouter, HTTPException, status

from app.schemas.maps import (
    EircodeGeocodeRequest,
    GeocodeRequest,
    GeocodeResponse,
    GeocodeResult,
    ReverseGeocodeRequest,
)
from app.services.google_maps import (
    geocode_address,
    geocode_eircode,
    is_configured,
    reverse_geocode,
)

router = APIRouter(prefix="/api/v1", tags=["maps"])


# ==============================================================================
# Health Check
# ==============================================================================


@router.get("/health")
async def health_check() -> dict:
    """Service health check.

    Returns:
        Health status with maps availability flag.
    """
    return {
        "status": "healthy",
        "service": "maps-access-service",
        "version": "1.0.0",
        "maps_configured": is_configured(),
    }


@router.get("/ready")
async def readiness_check() -> dict:
    """Readiness check for Kubernetes traffic routing."""
    maps_configured = is_configured()
    if not maps_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google Maps server key is not configured",
        )
    return {
        "status": "ready",
        "service": "maps-access-service",
        "maps_configured": maps_configured,
    }


# ==============================================================================
# Geocoding Endpoints
# ==============================================================================


@router.post("/maps/geocode", response_model=GeocodeResponse)
async def geocode(request: GeocodeRequest) -> GeocodeResponse:
    """Forward-geocode an address to coordinates.

    Args:
        request: Address to geocode.

    Returns:
        Coordinates, formatted address, and Eircode (if found).
    """
    if not is_configured():
        return GeocodeResponse(
            available=False,
            success=False,
            error="Google Maps service is not configured",
        )

    result = await geocode_address(request.address)
    if result is None:
        return GeocodeResponse(
            success=False,
            error=f"Could not geocode address: {request.address}",
        )

    return GeocodeResponse(
        success=True,
        result=GeocodeResult(**result),
    )


@router.post("/maps/reverse-geocode", response_model=GeocodeResponse)
async def reverse_geocode_endpoint(
    request: ReverseGeocodeRequest,
) -> GeocodeResponse:
    """Reverse-geocode coordinates to an address.

    Args:
        request: Latitude and longitude.

    Returns:
        Address, Eircode, and the original coordinates.
    """
    if not is_configured():
        return GeocodeResponse(
            available=False,
            success=False,
            error="Google Maps service is not configured",
        )

    result = await reverse_geocode(request.latitude, request.longitude)
    if result is None:
        return GeocodeResponse(
            success=False,
            error=f"Could not reverse-geocode ({request.latitude}, {request.longitude})",
        )

    return GeocodeResponse(
        success=True,
        result=GeocodeResult(**result),
    )


@router.post("/maps/geocode-eircode", response_model=GeocodeResponse)
async def geocode_eircode_endpoint(
    request: EircodeGeocodeRequest,
) -> GeocodeResponse:
    """Geocode an Irish Eircode to coordinates and address.

    Args:
        request: Eircode to resolve.

    Returns:
        Coordinates, formatted address, and the Eircode.
    """
    if not is_configured():
        return GeocodeResponse(
            available=False,
            success=False,
            error="Google Maps service is not configured",
        )

    result = await geocode_eircode(request.eircode)
    if result is None:
        return GeocodeResponse(
            success=False,
            error=f"Could not geocode Eircode: {request.eircode}",
        )

    return GeocodeResponse(
        success=True,
        result=GeocodeResult(**result),
    )
