from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List, Union, Literal
from datetime import datetime

class GeometryPoint(BaseModel):
    type: Literal["Point"] = "Point"
    coordinates: List[float] = Field(..., min_items=2, max_items=2)  # [lng, lat]

class GeometryLineString(BaseModel):
    type: Literal["LineString"] = "LineString"
    coordinates: List[List[float]] = Field(..., min_items=2)  # [[lng, lat], [lng, lat], ...]

class GeometryPolygon(BaseModel):
    type: Literal["Polygon"] = "Polygon"
    coordinates: List[List[List[float]]] = Field(..., min_items=1)  # [[[lng, lat], [lng, lat], ...]]

class FeatureCreateRequest(BaseModel):
    map_id: str = Field(..., description="UUID de la carte")
    name: Optional[str] = Field(None, description="Nom de la feature")
    type: str = Field(..., description="Type: point, polyline, polygon, zone, arrow")
    geometry: Union[GeometryPoint, GeometryLineString, GeometryPolygon] = Field(..., description="Géométrie GeoJSON")
    color: Optional[str] = Field("#000000", description="Couleur de la feature")
    stroke_width: Optional[int] = Field(2, description="Épaisseur du trait")
    opacity: Optional[float] = Field(1.0, description="Opacité (0.0-1.0)")
    z_index: Optional[int] = Field(1, description="Ordre d'affichage")
    tags: Optional[Dict[str, Any]] = Field(None, description="Tags personnalisés")
    start_date: Optional[datetime] = Field(None, description="Date de début")
    end_date: Optional[datetime] = Field(None, description="Date de fin")
    precision: Optional[str] = Field(None, description="Précision de la donnée")
    source: Optional[str] = Field(None, description="Source de la donnée")

    class Config:
        from_attributes = True

class FeatureUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, description="Nom de la feature")
    type: Optional[str] = Field(None, description="Type: point, polyline, polygon, zone, arrow")
    geometry: Optional[Union[GeometryPoint, GeometryLineString, GeometryPolygon]] = Field(None, description="Géométrie GeoJSON")
    color: Optional[str] = Field(None, description="Couleur de la feature")
    stroke_width: Optional[int] = Field(None, description="Épaisseur du trait")
    opacity: Optional[float] = Field(None, description="Opacité (0.0-1.0)")
    z_index: Optional[int] = Field(None, description="Ordre d'affichage")
    tags: Optional[Dict[str, Any]] = Field(None, description="Tags personnalisés")
    start_date: Optional[datetime] = Field(None, description="Date de début")
    end_date: Optional[datetime] = Field(None, description="Date de fin")
    precision: Optional[str] = Field(None, description="Précision de la donnée")
    source: Optional[str] = Field(None, description="Source de la donnée")

    class Config:
        from_attributes = True