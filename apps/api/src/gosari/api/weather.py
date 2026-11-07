"""제주 지도 날씨 조회."""

from datetime import date as CalendarDate
from datetime import timedelta
from typing import Annotated

from litestar import Controller, get
from litestar.concurrency import sync_to_thread
from litestar.exceptions import HTTPException
from litestar.params import QueryParameter

from gosari.agent.analysis import get_evidence_store
from gosari.sources.weather import WeatherResponse, korea_today, weather_service


class WeatherController(Controller):
    path = "/weather"

    @get("/")
    async def get_weather(
        self, date: Annotated[CalendarDate | None, QueryParameter()] = None
    ) -> WeatherResponse:
        selected = date or korea_today()
        if selected < CalendarDate(1940, 1, 1):
            raise HTTPException(status_code=400, detail="1940년 이후 날짜를 선택해 주세요.")
        if selected > korea_today() + timedelta(days=15):
            raise HTTPException(status_code=400, detail="예보는 15일 뒤까지 조회할 수 있습니다.")
        weather = await weather_service.get(selected)
        if weather.status != "unavailable":
            evidence_id = await sync_to_thread(
                get_evidence_store().put,
                {
                    "public_query_spec": {
                        "operation": "forecast_compare",
                        "source_ids": ["open_meteo"],
                        "forecast_target_times": [f"{selected.isoformat()}T12:00:00+09:00"],
                    },
                    "source_manifests": [
                        {
                            "source_id": "open_meteo",
                            "dataset_id": "jeju_weather",
                            "source_mode": "fetched",
                            "fetched_at": weather.updated_at,
                            "observed_period": {"date": selected.isoformat()},
                        }
                    ],
                    "result_values": weather.model_dump(mode="json", exclude={"evidence_ids"}),
                    "created_at": weather.updated_at,
                }
            )
            return weather.model_copy(update={"evidence_ids": [evidence_id]})
        return weather
