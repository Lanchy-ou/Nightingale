import type { Event } from '../types';
import EventCard from './EventCard';

export default function Timeline({
  events,
  focusEventId,
}: {
  events: Event[];
  focusEventId: string | null;
}) {
  return (
    <div className="timeline">
      <h2>Timeline</h2>
      {events.map((e) => (
        <EventCard key={e.event_id} event={e} focusEventId={focusEventId} />
      ))}
    </div>
  );
}
