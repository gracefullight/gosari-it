import { ArrowBendUpLeftIcon } from "@phosphor-icons/react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { getChatReplySuggestions } from "@/lib/chat-reply-suggestions";
import type { ChatMessage } from "@/stores/chat.atoms";

interface ChatReplySuggestionsProps {
  messages: readonly ChatMessage[];
  pending?: boolean;
  voiceActive?: boolean;
  onSend: (text: string) => void | Promise<void>;
}

export function ChatReplySuggestions({
  messages,
  pending = false,
  voiceActive = false,
  onSend,
}: ChatReplySuggestionsProps) {
  const [sending, setSending] = useState(false);
  const suggestions = getChatReplySuggestions(messages);
  if (pending || voiceActive || sending || suggestions.length === 0) return null;
  return (
    <fieldset aria-label="이어 물어보기" className="m-0 flex min-w-0 flex-wrap gap-2 border-0 p-0">
      {suggestions.map((text) => (
        <Button
          key={text}
          variant="outline"
          size="lg"
          className="min-h-11 max-w-full justify-start rounded-full px-4 py-2 text-left text-base whitespace-normal"
          onClick={async () => {
            if (sending) return;
            setSending(true);
            try {
              await onSend(text);
            } catch {
              // The existing send flow owns the error message and retry state.
            } finally {
              setSending(false);
            }
          }}
        >
          <ArrowBendUpLeftIcon aria-hidden="true" className="size-4 shrink-0" />
          <span>{text}</span>
        </Button>
      ))}
    </fieldset>
  );
}
