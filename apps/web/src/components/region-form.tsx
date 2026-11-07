import { useAtomValue } from "jotai";
import { useCallback, useEffect, useState } from "react";
import { DaumAddressSearch } from "@/components/daum-address-search";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useChat } from "@/hooks/use-chat";
import { ApiError, api } from "@/lib/gosari.api";
import type { Preview, PrivateRegion, Station } from "@/lib/gosari.types";
import { revisionCounterAtom } from "@/stores/chat.atoms";

interface RegionFormProps {
  onPreview: (preview: Preview) => void;
  hideStationCompare?: boolean;
}

export function RegionForm({ onPreview, hideStationCompare = false }: RegionFormProps) {
  const { confirmSpec } = useChat();
  const revisionCounter = useAtomValue(revisionCounterAtom);
  const [alias, setAlias] = useState("");
  const [area, setArea] = useState("");
  const [kind, setKind] = useState<"existing" | "interest">("interest");
  const [editingRegion, setEditingRegion] = useState<PrivateRegion | null>(null);
  const [regions, setRegions] = useState<PrivateRegion[]>([]);
  const [stations, setStations] = useState<Station[]>([]);
  const [stationA, setStationA] = useState("선흘");
  const [stationB, setStationB] = useState("제주(184)");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [addressSearchOpen, setAddressSearchOpen] = useState(false);

  const loadMapAndRegions = useCallback(async () => {
    try {
      const [mapRes, regRes] = await Promise.all([
        hideStationCompare ? Promise.resolve(null) : api.mapsPrepare(),
        api.regionsList(),
      ]);
      if (mapRes) setStations(mapRes.stations);
      setRegions(regRes.regions);
    } catch {
      // 초기 로드 실패 시 무시
    }
  }, [hideStationCompare]);

  // biome-ignore lint/correctness/useExhaustiveDependencies: Approved personal changes invalidate the persisted region list.
  useEffect(() => {
    void loadMapAndRegions();
  }, [loadMapAndRegions, revisionCounter]);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const payload = {
        kind,
        local_alias: alias.trim(),
        public_area_code: area.trim(),
      };
      const preview = editingRegion
        ? await api.regionsPrepare(payload, "update", editingRegion.region_id)
        : await api.regionsPrepare(payload, "create");
      onPreview(preview);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "미리보기 생성 실패");
    } finally {
      setBusy(false);
    }
  }

  async function requestDeleteRegion(regionId: string) {
    setBusy(true);
    setError(null);
    try {
      const preview = await api.regionsPrepare({}, "delete", regionId);
      onPreview(preview);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "삭제 미리보기 생성 실패");
    } finally {
      setBusy(false);
    }
  }

  function runRegionCompare() {
    confirmSpec(
      {
        operation: "region_compare",
        source_ids: ["jeju_579", "kma_asos"],
        station_selections: [
          { source_id: "jeju_579", station_name: stationA.trim() },
          { source_id: "kma_asos", station_name: stationB.trim() },
        ],
        years: [2024],
        month_day_start: "04-01",
        month_day_end: "05-31",
        elements: ["daily_rainfall", "average_temperature"],
      },
      `지역별 관측 비교 (${stationA} vs ${stationB})`
    );
  }

  return (
    <div className="max-w-full rounded-2xl border border-border bg-card p-5 shadow-sm">
      <h2 className="mb-4 text-lg font-semibold text-foreground">관심 지역</h2>

      {!hideStationCompare ? (
        <div className="mb-5 rounded-xl bg-muted/60 p-4">
          <p className="mb-2 text-base font-bold text-accent-foreground">
            관측소 비교 및 지도·목록
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <div className="grid gap-1">
              <Label htmlFor="station-a">기준 지역 관측소 (예: 선흘)</Label>
              <Input
                id="station-a"
                value={stationA}
                onChange={(e) => setStationA(e.target.value)}
              />
            </div>
            <div className="grid gap-1">
              <Label htmlFor="station-b">비교 지역 관측소 (예: 제주(184))</Label>
              <Input
                id="station-b"
                value={stationB}
                onChange={(e) => setStationB(e.target.value)}
              />
            </div>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button
              size="sm"
              onClick={runRegionCompare}
              disabled={!stationA.trim() || !stationB.trim()}
            >
              두 관측소 비교 실행
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() =>
                confirmSpec(
                  { operation: "station_search", source_ids: ["jeju_578"] },
                  "제주 관측소 지도·목록 보기"
                )
              }
            >
              관측소 지도·목록 보기 ({stations.length || 44}개 지점)
            </Button>
          </div>
        </div>
      ) : null}

      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <p className="text-base font-bold text-foreground">
            {editingRegion ? `등록 지역 수정 (${editingRegion.local_alias})` : "관심 지역 등록"}
          </p>
          {editingRegion ? (
            <Button
              variant="outline"
              size="xs"
              onClick={() => {
                setEditingRegion(null);
                setAlias("");
                setArea("");
              }}
            >
              새 지역 등록으로 전환
            </Button>
          ) : null}
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="region-alias">지역 별칭 (예: 자주 가는 동쪽 중산간)</Label>
          <Input id="region-alias" value={alias} onChange={(e) => setAlias(e.target.value)} />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="region-area">대략 지역 (예: 제주특별자치도 제주시 조천읍)</Label>
          <div className="flex gap-2">
            <Input id="region-area" value={area} onChange={(e) => setArea(e.target.value)} />
            <Button variant="outline" onClick={() => setAddressSearchOpen(true)}>
              주소 검색
            </Button>
          </div>
        </div>
        <div className="flex gap-4">
          <label className="flex min-h-10 cursor-pointer items-center gap-2 text-base">
            <input
              type="radio"
              name="region-kind"
              checked={kind === "existing"}
              onChange={() => setKind("existing")}
              className="size-4 accent-[var(--primary)]"
            />
            기존 이용 지역
          </label>
          <label className="flex min-h-10 cursor-pointer items-center gap-2 text-base">
            <input
              type="radio"
              name="region-kind"
              checked={kind === "interest"}
              onChange={() => setKind("interest")}
              className="size-4 accent-[var(--primary)]"
            />
            새 관심 지역
          </label>
        </div>
        <Button onClick={submit} disabled={busy || !alias.trim() || !area.trim()}>
          {editingRegion ? "지역 수정 미리보기" : "지역 등록 미리보기"}
        </Button>
      </div>

      {regions.length > 0 ? (
        <div className="mt-5 border-t border-border pt-4">
          <p className="mb-2 text-base font-bold text-foreground">
            등록한 지역 ({regions.length}건)
          </p>
          <ul className="flex flex-col gap-2 text-base">
            {regions.map((r) => (
              <li
                key={r.region_id}
                className="flex items-center justify-between rounded-xl border border-border bg-muted/40 px-3.5 py-2.5"
              >
                <span>
                  <strong>{r.local_alias}</strong> (
                  {r.kind === "existing" ? "기존 지역" : "관심 지역"}) ·{" "}
                  {r.public_area_code ?? r.coarse_grid}
                </span>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="xs"
                    onClick={() => {
                      setEditingRegion(r);
                      setAlias(r.local_alias);
                      setArea(r.public_area_code ?? "");
                      setKind(r.kind);
                    }}
                  >
                    수정
                  </Button>
                  <Button
                    variant="destructive"
                    size="xs"
                    onClick={() => void requestDeleteRegion(r.region_id)}
                  >
                    삭제
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {addressSearchOpen ? (
        <Dialog open onOpenChange={setAddressSearchOpen}>
          <DialogContent className="sm:max-w-xl">
            <DialogHeader>
              <DialogTitle>관심 지역 주소 검색</DialogTitle>
            </DialogHeader>
            <DaumAddressSearch
              onSelect={(address) => {
                setArea(address);
                setAddressSearchOpen(false);
              }}
            />
          </DialogContent>
        </Dialog>
      ) : null}
      {error ? (
        <p className="mt-2 text-base text-destructive" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
