export const ONBOARDING_STORAGE_KEY = "gosari_onboarding_v1";
export const ONBOARDING_TASKS = [
  {
    id: "weather",
    title: "제주 날씨 보기",
    path: "/outing",
    description: "날짜를 고르고 지도에서 지역별 기온과 강수확률을 확인하세요.",
  },
  {
    id: "region",
    title: "관심 지역 저장",
    path: "/regions",
    description: "지도를 눌러 핀을 찍고 관심 지역 이름을 저장하세요.",
  },
  {
    id: "notebook",
    title: "수첩 기록하기",
    path: "/notebook/new",
    description: "채취 날짜·위치·경험을 기록하고 저장하세요.",
  },
  {
    id: "share",
    title: "나눔 기록하기",
    path: "/share",
    description: "지인을 등록하고 날짜와 나눈 분량을 기록하세요.",
  },
  {
    id: "prices",
    title: "가격 조회",
    path: "/prices",
    description: "소매·지역 조사가·도매를 골라 가격을 확인하세요.",
  },
] as const;
export type OnboardingTaskId = (typeof ONBOARDING_TASKS)[number]["id"];
