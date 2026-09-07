import { eventLabel, formatDate, formatDateTime } from '../clinical';
import type { Event } from '../types';

type TimelineItem =
  | { kind: 'event'; key: string; events: [Event] }
  | { kind: 'encounter'; key: string; encounterId: string; events: Event[] };

export function buildTimelineItems(events: Event[]): TimelineItem[] {
  const sorted = [...events].sort(
    (a, b) => a.started_at.localeCompare(b.started_at) || a.event_id.localeCompare(b.event_id),
  );
  const byEncounter = new Map<string, Event[]>();
  for (const event of sorted) {
    if (!event.encounter_id) continue;
    const group = byEncounter.get(event.encounter_id) ?? [];
    group.push(event);
    byEncounter.set(event.encounter_id, group);
  }

  const emitted = new Set<string>();
  const items: TimelineItem[] = [];
  for (const event of sorted) {
    if (!event.encounter_id) {
      items.push({ kind: 'event', key: event.event_id, events: [event] });
      continue;
    }
    if (emitted.has(event.encounter_id)) continue;
    emitted.add(event.encounter_id);
    items.push({
      kind: 'encounter',
      key: `encounter:${event.encounter_id}`,
      encounterId: event.encounter_id,
      events: byEncounter.get(event.encounter_id) ?? [event],
    });
  }
  return items;
}

function EventButton({ event, onOpen }: { event: Event; onOpen: (event: Event) => void }) {
  return (
    <button className="timeline-event-button" onClick={() => onOpen(event)}>
      <span className="timeline-node" aria-hidden="true" />
      <span className="timeline-event-copy">
        <span className="timeline-event-kind">{event.event_type.startsWith('patient_') ? 'Patient update' : 'Clinical record'}</span>
        <strong>{eventLabel(event)}</strong>
        <small>{formatDateTime(event.started_at)}</small>
      </span>
      <span className="timeline-artifact-count">{event.artifact_count} documents</span>
      <span className="timeline-open-event">Open <span aria-hidden="true">→</span></span>
    </button>
  );
}

export default function ClinicalTimeline({
  events,
  onOpenEvent,
  eventType,
  setEventType,
  newestFirst,
  setNewestFirst,
}: {
  events: Event[];
  onOpenEvent: (event: Event) => void;
  eventType: string;
  setEventType: (value: string) => void;
  newestFirst: boolean;
  setNewestFirst: (value: boolean) => void;
}) {
  const eventTypes = [...new Set(events.map((event) => event.event_type))];
  const filtered = eventType === 'all' ? events : events.filter((event) => event.event_type === eventType);
  const chronologicalItems = buildTimelineItems(filtered);
  const items = newestFirst ? [...chronologicalItems].reverse() : chronologicalItems;
  return (
    <section className="clinical-view" aria-labelledby="timeline-heading">
      <div className="view-title-row">
        <div>
          <p className="eyebrow">Longitudinal record</p>
          <h2 id="timeline-heading">Timeline</h2>
          <p className="view-subtitle">Follow the care journey. Open a visit to read its documents and discussion.</p>
        </div>
        <span className="record-count">{events.length} events</span>
      </div>
      <div className="timeline-controls">
        <label>Event type <select value={eventType} onChange={(event) => setEventType(event.target.value)}><option value="all">All events</option>{eventTypes.map((type) => <option key={type} value={type}>{eventLabel(events.find((event) => event.event_type === type)!)}</option>)}</select></label>
        <button className="secondary-button" onClick={() => setNewestFirst(!newestFirst)}>{newestFirst ? 'Newest first ↓' : 'Oldest first ↑'}</button>
      </div>
      {items.length === 0 && (
        <div className="empty-state">
          <h3>No clinical events yet</h3>
          <p>Create a Doctor Consult to begin this patient's longitudinal record.</p>
        </div>
      )}
      <div className="clinical-timeline-list">
        {items.map((item) => {
          if (item.kind === 'event') {
            const event = item.events[0];
            return (
              <article className="timeline-single" key={item.key}>
                <div className="timeline-date-label">{formatDate(event.started_at)}</div>
                <EventButton event={event} onOpen={onOpenEvent} />
              </article>
            );
          }
          return (
            <article className="encounter-group" key={item.key}>
              <header>
                <div>
                  <span className="encounter-kicker">Clinic Visit</span>
                  <h3>{formatDate(item.events[0].started_at)}</h3>
                </div>
                <span className="encounter-id" title={`Encounter ${item.encounterId}`}>
                  One encounter · {item.events.length} event{item.events.length === 1 ? '' : 's'}
                </span>
              </header>
              <div className="encounter-events">
                {item.events.map((event) => (
                  <EventButton key={event.event_id} event={event} onOpen={onOpenEvent} />
                ))}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
