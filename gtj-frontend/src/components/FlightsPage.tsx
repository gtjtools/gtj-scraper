import { Aircraft, mockOperators } from '../lib/mock-data';
import { SearchCriteria } from './SearchForm';
import { AircraftCard } from './AircraftCard';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Filter, SlidersHorizontal, Plane, MapPin, Building2 } from 'lucide-react';

interface FlightsPageProps {
  searchResults: Aircraft[];
  searchCriteria: SearchCriteria | null;
  onAddToShortlist: (aircraft: Aircraft) => void;
  onViewDetails: (aircraft: Aircraft) => void;
  shortlistedIds: string[];
}

export function FlightsPage({
  searchResults,
  searchCriteria,
  onAddToShortlist,
  onViewDetails,
  shortlistedIds
}: FlightsPageProps) {
  // Group aircraft by location when searching by operator
  const groupedByLocation = searchCriteria?.searchType === 'operator'
    ? searchResults.reduce((acc, aircraft) => {
        const location = aircraft.operator.baseLocation || 'Unknown Location';
        if (!acc[location]) {
          acc[location] = [];
        }
        acc[location].push(aircraft);
        return acc;
      }, {} as Record<string, Aircraft[]>)
    : null;

  const showGrouped = groupedByLocation && Object.keys(groupedByLocation).length > 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h1 className="text-3xl font-bold">
            {searchResults.length} Aircraft Available
          </h1>
          {searchCriteria && (
            <div className="flex gap-2 flex-wrap">
              {searchCriteria.searchType === 'tail' && searchCriteria.tailNumbers && (
                <>
                  <Badge variant="secondary" className="text-sm gap-1">
                    <Plane className="h-3 w-3" />
                    {searchCriteria.tailNumbers.length} tail{searchCriteria.tailNumbers.length !== 1 ? 's' : ''}
                  </Badge>
                  {searchCriteria.tailNumbers.slice(0, 2).map((tail) => (
                    <Badge key={tail} variant="outline" className="text-sm font-mono">
                      {tail}
                    </Badge>
                  ))}
                  {searchCriteria.tailNumbers.length > 2 && (
                    <Badge variant="outline" className="text-sm">
                      +{searchCriteria.tailNumbers.length - 2} more
                    </Badge>
                  )}
                </>
              )}
              {searchCriteria.searchType === 'airport' && (
                <>
                  {searchCriteria.departureAirport && searchCriteria.arrivalAirport && (
                    <Badge variant="secondary" className="text-sm gap-1">
                      <MapPin className="h-3 w-3" />
                      {searchCriteria.departureAirport.split(' - ')[0]} → {searchCriteria.arrivalAirport.split(' - ')[0]}
                    </Badge>
                  )}
                  {searchCriteria.departureAirport && !searchCriteria.arrivalAirport && (
                    <Badge variant="secondary" className="text-sm gap-1">
                      <MapPin className="h-3 w-3" />
                      From {searchCriteria.departureAirport.split(' - ')[0]}
                    </Badge>
                  )}
                  {!searchCriteria.departureAirport && searchCriteria.arrivalAirport && (
                    <Badge variant="secondary" className="text-sm gap-1">
                      <MapPin className="h-3 w-3" />
                      To {searchCriteria.arrivalAirport.split(' - ')[0]}
                    </Badge>
                  )}
                </>
              )}
              {searchCriteria.searchType === 'operator' && searchCriteria.operatorIds && (
                <Badge variant="secondary" className="text-sm gap-1">
                  <Building2 className="h-3 w-3" />
                  {searchCriteria.operatorIds.length} operator{searchCriteria.operatorIds.length !== 1 ? 's' : ''}
                </Badge>
              )}
            </div>
          )}
        </div>
        <div className="flex gap-2">
          <Button variant="outline" className="gap-2">
            <SlidersHorizontal className="h-4 w-4" />
            Sort
          </Button>
          <Button variant="outline" className="gap-2">
            <Filter className="h-4 w-4" />
            Filter
          </Button>
        </div>
      </div>

      {/* Results Grid */}
      {searchResults.length === 0 ? (
        <div className="bg-white rounded-2xl shadow-md p-12 text-center">
          <p className="text-muted-foreground mb-2">
            No aircraft match your search criteria
          </p>
          <p className="text-sm text-muted-foreground">
            Try adjusting your passenger count or aircraft type preferences
          </p>
        </div>
      ) : showGrouped ? (
        // Grouped by location view for operator searches
        <div className="space-y-8">
          {Object.entries(groupedByLocation!).map(([location, aircraft]) => (
            <div key={location} className="space-y-4">
              <div className="flex items-center gap-2 pb-2 border-b">
                <MapPin className="h-5 w-5 text-muted-foreground" />
                <h2 className="text-xl font-semibold">{location}</h2>
                <Badge variant="secondary" className="ml-2">
                  {aircraft.length} aircraft
                </Badge>
              </div>
              <div className="grid gap-6 md:grid-cols-1 lg:grid-cols-2">
                {aircraft.map((ac) => (
                  <AircraftCard
                    key={ac.id}
                    aircraft={ac}
                    onAddToShortlist={onAddToShortlist}
                    onViewDetails={onViewDetails}
                    isShortlisted={shortlistedIds.includes(ac.id)}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        // Standard grid view for tail number and airport searches
        <div className="grid gap-6 md:grid-cols-1 lg:grid-cols-2">
          {searchResults.map((aircraft) => (
            <AircraftCard
              key={aircraft.id}
              aircraft={aircraft}
              onAddToShortlist={onAddToShortlist}
              onViewDetails={onViewDetails}
              isShortlisted={shortlistedIds.includes(aircraft.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
