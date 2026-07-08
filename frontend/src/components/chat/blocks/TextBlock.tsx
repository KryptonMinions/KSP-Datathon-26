import type { TextBlock as TextBlockType } from "@/lib/types/content-blocks";
import { CitationChip } from "@/components/shared/CitationChip";

export function TextBlock({ block }: { block: TextBlockType }) {
  return (
    <div className="space-y-2">
      <p className="text-sm leading-relaxed">{block.content}</p>
      {block.citations && block.citations.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {block.citations.map((citation, i) => (
            <CitationChip key={`${citation.firId}-${i}`} citation={citation} />
          ))}
        </div>
      )}
    </div>
  );
}
