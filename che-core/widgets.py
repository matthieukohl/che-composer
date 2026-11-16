"""CHE-only map field: GeoJSON maps to CHEEvent.spatial_area (JSONField).

Unlike CAP's polygon widget, this does not require a GIS GeometryField,
CAP severity, or CAP area registry. No CAP source files are modified.
"""
from django import forms


class CHESpatialAreaWidget(forms.Widget):
    template_name = "che/widgets/spatial_area_map.html"

    def format_value(self, value):
        import json
        if value is None or value == "":
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        return str(value)

    def value_from_datadict(self, data, files, name):
        # JSONField's normal form field parses the submitted JSON string.
        return data.get(name, "")

    @property
    def media(self):
        return forms.Media(
            css={"all": [
                "capeditor/css/maplibre-gl.css",
                "capeditor/css/mapbox-gl-draw.css",
            ]},
            js=[
                "capeditor/js/maplibre-gl.js",
                "capeditor/js/mapbox-gl-draw.js",
                "che/js/spatial-area-map.js",
            ],
        )
