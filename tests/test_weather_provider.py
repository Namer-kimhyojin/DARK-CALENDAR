# -*- coding: utf-8 -*-
from pathlib import Path
import unittest

from calendar_app.infrastructure.weather.geonames import find_city
from calendar_app.infrastructure.weather.met_norway import (
    parse_locationforecast,
    symbol_code_to_wmo,
)


class WeatherProviderTests(unittest.TestCase):
    def test_bundled_geonames_finds_localized_city_name(self):
        city = find_city("서울")

        self.assertIsNotNone(city)
        self.assertEqual(city.country_code, "KR")
        self.assertAlmostEqual(city.latitude, 37.566, places=3)
        self.assertAlmostEqual(city.longitude, 126.9784, places=3)

    def test_country_code_disambiguates_city(self):
        city = find_city("New York, US")

        self.assertIsNotNone(city)
        self.assertEqual(city.country_code, "US")
        self.assertGreater(city.population, 1_000_000)

    def test_locationforecast_parser_converts_units_and_symbol(self):
        payload = {
            "properties": {
                "timeseries": [
                    {
                        "data": {
                            "instant": {
                                "details": {
                                    "air_temperature": 20.0,
                                    "relative_humidity": 55.2,
                                    "wind_speed": 3.4,
                                }
                            },
                            "next_1_hours": {"summary": {"symbol_code": "partlycloudy_day"}},
                        }
                    }
                ]
            }
        }

        parsed = parse_locationforecast(payload, "Seoul", "fahrenheit")

        self.assertEqual(parsed["city"], "Seoul")
        self.assertEqual(parsed["temp"], "68")
        self.assertEqual(parsed["unit"], "°F")
        self.assertEqual(parsed["_wmo"], 2)
        self.assertEqual(parsed["humidity"], "55.2")
        self.assertEqual(parsed["wind"], "3.4")

    def test_met_symbol_mapping_covers_precipitation(self):
        self.assertEqual(symbol_code_to_wmo("heavyrainandthunder_night"), 95)
        self.assertEqual(symbol_code_to_wmo("heavysnow_day"), 75)
        self.assertEqual(symbol_code_to_wmo("rainshowers_day"), 80)

    def test_weather_privacy_notice_matches_provider(self):
        root = Path(__file__).resolve().parents[1]
        privacy = (root / "docs" / "privacy-policy.ko.md").read_text(
            encoding="utf-8", errors="strict"
        )

        self.assertIn("MET Norway", privacy)
        self.assertIn("GeoNames", privacy)
        self.assertNotIn("Open-Meteo", privacy)


if __name__ == "__main__":
    unittest.main()
