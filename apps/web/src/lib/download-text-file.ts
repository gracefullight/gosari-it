/** 브라우저에서 텍스트 파일 1개를 내려받게 한다. 서버에는 파일을 남기지 않는다. */
export function downloadTextFile(filename: string, content: string): void {
  if (typeof document === "undefined" || typeof URL.createObjectURL !== "function") return;
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}
