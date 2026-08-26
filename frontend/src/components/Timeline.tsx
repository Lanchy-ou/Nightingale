import type { Event } from '../types';
import EventCard from './EventCard';

export default function Timeline({ events }: { events: Event[] }) {
  return (
    <div className="timeline">
      <h2>Timeline</h2>
      {events.map((e) => (
        <EventCard key={e.event_id} event={e} />
      ))}
    </div>
  );
}
