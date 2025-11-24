import { Aircraft } from '../lib/mock-data';
import { TrustScoreGauge } from './TrustScoreGauge';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Card } from './ui/card';
import { Plane, Users, Gauge, MapPin, Calendar, AlertCircle, Check } from 'lucide-react';

interface AircraftCardProps {
  aircraft: Aircraft;
  onAddToShortlist: (aircraft: Aircraft) => void;
  onViewDetails: (aircraft: Aircraft) => void;
  isShortlisted?: boolean;
}

export function AircraftCard({ aircraft, onAddToShortlist, onViewDetails, isShortlisted = false }: AircraftCardProps) {
  const getAvailabilityColor = (status: string) => {
    switch (status) {
      case 'available':
        return 'bg-green-100 text-green-800 border-green-200';
      case 'limited':
        return 'bg-amber-100 text-amber-800 border-amber-200';
      case 'unavailable':
        return 'bg-red-100 text-red-800 border-red-200';
      default:
        return 'bg-gray-100 text-gray-800 border-gray-200';
    }
  };

  return (
    <Card className="overflow-hidden hover:shadow-lg transition-shadow">
      <div className="p-6">
        <div className="flex justify-between items-start mb-4">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-2">
              <h3 className="text-xl font-semibold font-mono">
                {aircraft.tailNumber}
              </h3>
              <Badge variant="outline" className={getAvailabilityColor(aircraft.availability)}>
                {aircraft.availability}
              </Badge>
            </div>
            <p className="text-muted-foreground">
              {aircraft.manufacturer} {aircraft.model} • {aircraft.year}
            </p>
          </div>
          <TrustScoreGauge score={aircraft.operator.trustScore} size="sm" />
        </div>

        <div className="space-y-3 mb-4">
          <div className="flex items-center gap-2 text-sm">
            <Users className="h-4 w-4 text-muted-foreground" />
            <span>Up to {aircraft.capacity} passengers</span>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <Gauge className="h-4 w-4 text-muted-foreground" />
            <span>Range: {aircraft.range.toLocaleString()} nm</span>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <MapPin className="h-4 w-4 text-muted-foreground" />
            <span>{aircraft.operator.name} • {aircraft.operator.baseLocation}</span>
          </div>
        </div>

        <div className="flex items-center gap-2 mb-4">
          {aircraft.operator.argusRating && (
            <Badge variant="secondary" className="text-xs">
              ARGUS {aircraft.operator.argusRating}
            </Badge>
          )}
          {aircraft.operator.wyvernRating && (
            <Badge variant="secondary" className="text-xs">
              Wyvern {aircraft.operator.wyvernRating}
            </Badge>
          )}
          {aircraft.operator.aogIncidents === 0 && (
            <Badge variant="secondary" className="text-xs bg-green-100 text-green-800">
              No AOG
            </Badge>
          )}
          {aircraft.operator.aogIncidents > 0 && (
            <Badge variant="secondary" className="text-xs bg-amber-100 text-amber-800 flex items-center gap-1">
              <AlertCircle className="h-3 w-3" />
              {aircraft.operator.aogIncidents} AOG
            </Badge>
          )}
        </div>

        <div className="flex gap-2 pt-4 border-t">
          <Button
            variant="outline"
            onClick={() => onViewDetails(aircraft)}
            className="flex-1"
          >
            Details
          </Button>
          <Button
            onClick={() => onAddToShortlist(aircraft)}
            className={`flex-1 ${isShortlisted ? 'bg-green-600 hover:bg-green-700' : 'bg-[#335cff] hover:bg-[#2847cc]'}`}
            disabled={aircraft.availability === 'unavailable'}
          >
            {isShortlisted ? (
              <>
                <Check className="h-4 w-4 mr-2" />
                Shortlisted
              </>
            ) : (
              'Add to Shortlist'
            )}
          </Button>
        </div>
      </div>
    </Card>
  );
}
