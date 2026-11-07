export function ChatThinkingIndicator() {
  return (
    <div role="status" className="inline-flex min-h-6 items-center text-base text-muted-foreground">
      <span className="sr-only">답변 작성 중</span>
      <span aria-hidden="true" className="inline-flex w-8 text-2xl font-semibold leading-6">
        <span>.</span>
        <span className="animate-chat-thinking-second motion-reduce:animate-none motion-reduce:opacity-100">
          .
        </span>
        <span className="animate-chat-thinking-third motion-reduce:animate-none motion-reduce:opacity-100">
          .
        </span>
      </span>
    </div>
  );
}
