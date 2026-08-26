import type { Artifact, Span } from '../types';

function HighlightedText({
  text,
  offset,
  markRef,
}: {
  text: string;
  offset?: [number, number];
  markRef?: React.RefObject<HTMLElement>;
}) {
  if (!offset || offset[0] < 0 || offset[1] > text.length) return <>{text}</>;
  const [s, e] = offset;
  return (
    <>
      {text.slice(0, s)}
      <mark ref={markRef}>{text.slice(s, e)}</mark>
      {text.slice(e)}
    </>
  );
}

function matchOffset(span: Span | null, kind: string, key: number | string): [number, number] | undefined {
  if (span && span.kind === kind && span.index === key) return span.offset;
  return undefined;
}

export default function ArtifactContent({
  artifact,
  span,
  markRef,
}: {
  artifact: Artifact;
  span?: Span | null;
  markRef?: React.RefObject<HTMLElement>;
}) {
  const content = artifact.content;
  const s = span ?? null;

  if (Array.isArray(content.segments)) {
    return (
      <div className="artifact-content">
        {content.segments.map((seg: any) => (
          <div key={seg.index} className="line">
            <span className="speaker">{seg.speaker}</span>{' '}
            <HighlightedText text={seg.text} offset={matchOffset(s, 'segment', seg.index)} markRef={markRef} />
          </div>
        ))}
      </div>
    );
  }

  if (Array.isArray(content.messages)) {
    return (
      <div className="artifact-content">
        {content.messages.map((m: any, i: number) => (
          <div key={m.id ?? i} className="line">
            <span className="speaker">{m.speaker}</span>{' '}
            <HighlightedText text={m.text} offset={matchOffset(s, 'message', i + 1)} markRef={markRef} />
          </div>
        ))}
      </div>
    );
  }

  // Named string sections (clinician_note / patient_instruction / ai summary).
  return (
    <div className="artifact-content">
      {Object.entries(content)
        .filter(([, v]) => typeof v === 'string')
        .map(([k, v]) => (
          <div key={k} className="line">
            <span className="speaker">{k}</span>{' '}
            <HighlightedText text={v as string} offset={matchOffset(s, 'section', k)} markRef={markRef} />
          </div>
        ))}
      {Array.isArray(content.key_points) && (
        <ul className="key-points">
          {(content.key_points as string[]).map((kp, i) => (
            <li key={i}>{kp}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
