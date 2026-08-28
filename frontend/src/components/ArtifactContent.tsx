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

function messageOffset(span: Span | null, message: any, position: number): [number, number] | undefined {
  return matchOffset(span, 'message', typeof message.id === 'string' ? message.id : position)
    ?? matchOffset(span, 'message', position);
}

function sectionLabel(key: string): string {
  const labels: Record<string, string> = {
    assessment: 'Assessment',
    chief_complaint: 'Chief complaint',
    follow_up: 'Follow-up',
    instruction: 'Patient instruction',
    plan: 'Plan',
    summary: 'Summary',
  };
  return labels[key] ?? key.replace(/_/g, ' ').replace(/^./, (letter) => letter.toUpperCase());
}

function generationLabel(method: string | null | undefined, degraded: boolean | undefined): string {
  if (degraded) return 'Safe fallback';
  if (method === 'deepseek') return 'DeepSeek AI';
  return 'Local deterministic';
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
          <div key={seg.index} className={`line transcript-line speaker-${String(seg.speaker).toLowerCase().replace(/[^a-z0-9_-]/g, '-')}`}>
            <span className="speaker">{seg.speaker}</span>{' '}
            <HighlightedText text={seg.text} offset={matchOffset(s, 'segment', seg.index)} markRef={markRef} />
          </div>
        ))}
      </div>
    );
  }

  if (Array.isArray(content.messages)) {
    if (artifact.artifact_type === 'raw_conversation') {
      const patientMessages = content.messages.filter((message: any) => message.speaker === 'patient');
      const aiMessages = content.messages.filter((message: any) => message.speaker === 'ai');
      return (
        <div className="artifact-content checkin-artifact-content">
          {content.safety_status === 'safety_escalated' && (
            <div className="clinical-checkin-safety"><strong>Safety guidance shown</strong><p>Ordinary Check-in questions stopped. The system did not claim that the clinic was notified.</p></div>
          )}
          <section className="artifact-section checkin-source-section">
            <h4>Patient original messages</h4>
            {patientMessages.map((message: any) => {
              const position = content.messages.indexOf(message) + 1;
              return <div key={message.id ?? position} className="line checkin-source-line"><span className="speaker">Patient</span>{' '}<HighlightedText text={message.text} offset={messageOffset(s, message, position)} markRef={markRef} /></div>;
            })}
          </section>
          <section className="artifact-section checkin-ai-section">
            <h4>Nightingale AI questions and acknowledgements</h4>
            {aiMessages.map((message: any) => {
              const position = content.messages.indexOf(message) + 1;
              return <div key={message.id ?? position} className="line checkin-ai-line"><span className="speaker">{generationLabel(message.generation_method, message.degraded)}{message.question_type ? ` · ${String(message.question_type).replace(/_/g, ' ')}` : ''}</span>{' '}<HighlightedText text={message.text} offset={messageOffset(s, message, position)} markRef={markRef} /></div>;
            })}
          </section>
        </div>
      );
    }
    return (
      <div className="artifact-content">
        {content.messages.map((m: any, i: number) => (
          <div key={m.id ?? i} className={`line message-line speaker-${String(m.speaker).toLowerCase().replace(/[^a-z0-9_-]/g, '-')}`}>
            <span className="speaker">{m.speaker}</span>{' '}
            <HighlightedText text={m.text} offset={messageOffset(s, m, i + 1)} markRef={markRef} />
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
          <section key={k} className="artifact-section">
            <h4>{sectionLabel(k)}</h4>
            <p><HighlightedText text={v as string} offset={matchOffset(s, 'section', k)} markRef={markRef} /></p>
          </section>
        ))}
      {Array.isArray(content.key_points) && (
        <section className="artifact-section"><h4>Key points</h4><ul className="key-points">
          {(content.key_points as string[]).map((kp, i) => (
            <li key={i}>{kp}</li>
          ))}
        </ul></section>
      )}
      {Array.isArray(content.source_facts) && (
        <section className="artifact-section checkin-summary-sources"><h4>Exact patient sources</h4><ul>
          {(content.source_facts as any[]).map((fact) => (
            <li key={`${fact.patient_message_id}:${fact.quote}`}><strong>{fact.patient_message_id}</strong><span>{fact.quote}</span></li>
          ))}
        </ul></section>
      )}
    </div>
  );
}
