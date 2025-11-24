import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  MapPin,
  Navigation,
  Plane,
  Radio,
  Search,
  TrendingDown,
  Users,
  Wrench,
} from 'lucide-react';
import { TrackedFlight } from '../lib/mock-data';
import { TrustScoreGauge } from './TrustScoreGauge';
import { Alert, AlertDescription, AlertTitle } from './ui/alert';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Card } from './ui/card';
import { Separator } from './ui/separator';

interface TrackedFlightsPageProps {
  trackedFlights: TrackedFlight[];
  onViewAOGReport?: (flightId: string, aogReportId: string) => void;
  onFindReplacement?: (flight: TrackedFlight) => void;
}

export function TrackedFlightsPage({
  trackedFlights,
  onViewAOGReport,
  onFindReplacement,
}: TrackedFlightsPageProps) {
  const getStatusConfig = (status: TrackedFlight['status']) => {
    switch (status) {
      case 'at-departure':
        return {
          label: 'At Departure Airport',
          color: 'bg-blue-100 text-blue-800 border-blue-200',
          icon: MapPin,
          iconColor: 'text-blue-600',
        };
      case 'at-different-airport':
        return {
          label: 'At Different Airport',
          color: 'bg-amber-100 text-amber-800 border-amber-200',
          icon: MapPin,
          iconColor: 'text-amber-600',
        };
      case 'in-flight':
        return {
          label: 'In Flight',
          color: 'bg-green-100 text-green-800 border-green-200',
          icon: Plane,
          iconColor: 'text-green-600',
        };
      case 'under-maintenance':
        return {
          label: 'Under Maintenance',
          color: 'bg-red-100 text-red-800 border-red-200',
          icon: Wrench,
          iconColor: 'text-red-600',
        };
      case 'location-unknown':
        return {
          label: 'Location Unknown',
          color: 'bg-slate-100 text-slate-800 border-slate-200',
          icon: Radio,
          iconColor: 'text-slate-600',
        };
    }
  };

  const isWithin48Hours = (departureDate: string) => {
    const departure = new Date(departureDate);
    const now = new Date();
    const hoursDiff = (departure.getTime() - now.getTime()) / (1000 * 60 * 60);
    return hoursDiff > 0 && hoursDiff <= 48;
  };

  const getTripScoreColor = (score: number) => {
    if (score >= 90) return 'text-green-600';
    if (score >= 70) return 'text-blue-600';
    if (score >= 50) return 'text-amber-600';
    return 'text-red-600';
  };

  const activeFlights = trackedFlights.filter(
    (f) => f.status === 'in-flight' || f.status === 'at-departure'
  );
  const underMaintenanceFlights = trackedFlights.filter(
    (f) => f.status === 'under-maintenance'
  );
  const otherFlights = trackedFlights.filter(
    (f) =>
      f.status !== 'in-flight' &&
      f.status !== 'at-departure' &&
      f.status !== 'under-maintenance'
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold mb-2">Track Flights</h1>
          <p className="text-muted-foreground">
            Monitor booked flights in real-time with status updates and
            performance scores
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="gap-1">
            <Plane className="h-3 w-3" />
            {trackedFlights.length} Active Bookings
          </Badge>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid md:grid-cols-4 gap-4">
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <div className="rounded-full bg-green-100 p-2">
              <Plane className="h-5 w-5 text-green-600" />
            </div>
            <div>
              <p className="text-2xl font-bold">{activeFlights.length}</p>
              <p className="text-sm text-muted-foreground">In Flight / Ready</p>
            </div>
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-center gap-3">
            <div className="rounded-full bg-red-100 p-2">
              <AlertTriangle className="h-5 w-5 text-red-600" />
            </div>
            <div>
              <p className="text-2xl font-bold">
                {trackedFlights.filter((f) => f.hasAOG).length}
              </p>
              <p className="text-sm text-muted-foreground">AOG Incidents</p>
            </div>
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-center gap-3">
            <div className="rounded-full bg-blue-100 p-2">
              <Clock className="h-5 w-5 text-blue-600" />
            </div>
            <div>
              <p className="text-2xl font-bold">
                {
                  trackedFlights.filter((f) =>
                    isWithin48Hours(f.currentLeg.departureDate)
                  ).length
                }
              </p>
              <p className="text-sm text-muted-foreground">Within 48 Hours</p>
            </div>
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-center gap-3">
            <div className="rounded-full bg-amber-100 p-2">
              <TrendingDown className="h-5 w-5 text-amber-600" />
            </div>
            <div>
              <p className="text-2xl font-bold">
                {
                  trackedFlights.filter(
                    (f) => f.tripScore && f.tripScore.score < 70
                  ).length
                }
              </p>
              <p className="text-sm text-muted-foreground">Low TripScores</p>
            </div>
          </div>
        </Card>
      </div>

      {/* Under Maintenance Alert */}
      {underMaintenanceFlights.length > 0 && (
        <Alert className="border-red-200 bg-red-50">
          <AlertTriangle className="h-4 w-4 text-red-600" />
          <AlertTitle className="text-red-900">
            Aircraft Under Maintenance
          </AlertTitle>
          <AlertDescription className="text-red-800">
            {underMaintenanceFlights.length} flight
            {underMaintenanceFlights.length !== 1 ? 's' : ''} currently
            affected. Consider using Airport Search to find replacement
            aircraft.
          </AlertDescription>
        </Alert>
      )}

      {/* Tracked Flights List */}
      <div className="space-y-4">
        {trackedFlights.length === 0 ? (
          <Card className="p-12">
            <div className="flex flex-col items-center justify-center text-center">
              <div className="rounded-full bg-slate-100 p-6 mb-4">
                <Plane className="h-12 w-12 text-muted-foreground" />
              </div>
              <h3 className="font-semibold mb-2">No Active Flights</h3>
              <p className="text-sm text-muted-foreground max-w-sm">
                You don't have any booked flights to track at the moment.
                Flights will appear here once bookings are confirmed.
              </p>
            </div>
          </Card>
        ) : (
          trackedFlights.map((flight) => {
            const statusConfig = getStatusConfig(flight.status);
            const StatusIcon = statusConfig.icon;
            const within48Hours = isWithin48Hours(
              flight.currentLeg.departureDate
            );
            const showTripScore = within48Hours && flight.tripScore;
            const lowTripScore =
              flight.tripScore && flight.tripScore.score < 70;

            return (
              <Card key={flight.id} className="overflow-hidden">
                <div className="p-6">
                  {/* Header */}
                  <div className="flex items-start justify-between mb-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-2">
                        <h3 className="font-semibold font-mono">
                          {flight.bookingReference}
                        </h3>
                        <Badge variant="outline" className={statusConfig.color}>
                          <StatusIcon
                            className={`h-3 w-3 mr-1 ${statusConfig.iconColor}`}
                          />
                          {statusConfig.label}
                        </Badge>
                        {within48Hours && (
                          <Badge
                            variant="outline"
                            className="bg-blue-50 text-blue-700 border-blue-200"
                          >
                            <Clock className="h-3 w-3 mr-1" />
                            Departing Soon
                          </Badge>
                        )}
                      </div>
                      <p className="text-sm text-muted-foreground">
                        {flight.client.name} • {flight.client.company}
                      </p>
                    </div>

                    {/* TrustScore Gauge */}
                    <TrustScoreGauge
                      score={flight.aircraft.operator.trustScore}
                      size="sm"
                    />
                  </div>

                  {/* Flight Details */}
                  <div className="grid md:grid-cols-2 gap-6 mb-4">
                    {/* Left Column - Route & Aircraft */}
                    <div className="space-y-4">
                      <div>
                        <p className="text-xs text-muted-foreground mb-2">
                          Current Leg
                        </p>
                        <div className="flex items-center gap-3">
                          <div className="text-center">
                            <p className="font-mono font-semibold">
                              {flight.currentLeg.departure}
                            </p>
                            <p className="text-xs text-muted-foreground">
                              {new Date(
                                flight.currentLeg.departureDate
                              ).toLocaleDateString('en-US', {
                                month: 'short',
                                day: 'numeric',
                              })}
                            </p>
                            <p className="text-xs text-muted-foreground">
                              {new Date(
                                flight.currentLeg.departureDate
                              ).toLocaleTimeString('en-US', {
                                hour: '2-digit',
                                minute: '2-digit',
                              })}
                            </p>
                          </div>
                          <div className="flex-1">
                            <Separator className="relative">
                              <Plane className="h-4 w-4 absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-background text-muted-foreground rotate-90" />
                            </Separator>
                          </div>
                          <div className="text-center">
                            <p className="font-mono font-semibold">
                              {flight.currentLeg.arrival}
                            </p>
                            <p className="text-xs text-muted-foreground">
                              {new Date(
                                flight.currentLeg.arrivalDate
                              ).toLocaleDateString('en-US', {
                                month: 'short',
                                day: 'numeric',
                              })}
                            </p>
                            <p className="text-xs text-muted-foreground">
                              {new Date(
                                flight.currentLeg.arrivalDate
                              ).toLocaleTimeString('en-US', {
                                hour: '2-digit',
                                minute: '2-digit',
                              })}
                            </p>
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-2 text-sm">
                        <Navigation className="h-4 w-4 text-muted-foreground" />
                        <span className="font-semibold">
                          {flight.aircraft.tailNumber}
                        </span>
                        <span className="text-muted-foreground">
                          {flight.aircraft.manufacturer} {flight.aircraft.model}
                        </span>
                      </div>

                      <div className="flex items-center gap-2 text-sm">
                        <Users className="h-4 w-4 text-muted-foreground" />
                        <span>{flight.passengers} passengers</span>
                      </div>

                      {flight.currentLocation && (
                        <div className="flex items-center gap-2 text-sm">
                          <MapPin className="h-4 w-4 text-muted-foreground" />
                          <span>{flight.currentLocation}</span>
                        </div>
                      )}
                    </div>

                    {/* Right Column - TripScore & Status */}
                    <div className="space-y-4">
                      {/* TripScore */}
                      {showTripScore && (
                        <div
                          className={`p-4 rounded-lg border ${
                            lowTripScore
                              ? 'bg-red-50 border-red-200'
                              : 'bg-blue-50 border-blue-200'
                          }`}
                        >
                          <div className="flex items-center justify-between mb-3">
                            <div>
                              <p className="text-xs text-muted-foreground mb-1">
                                TripScore
                              </p>
                              <div className="flex items-baseline gap-2">
                                <p
                                  className={`text-3xl font-bold ${getTripScoreColor(
                                    flight.tripScore!.score
                                  )}`}
                                >
                                  {flight.tripScore!.score}
                                </p>
                                <span className="text-sm text-muted-foreground">
                                  /100
                                </span>
                              </div>
                              {flight.tripScore!.isFirstScore && (
                                <Badge
                                  variant="secondary"
                                  className="mt-1 text-xs"
                                >
                                  <CheckCircle2 className="h-3 w-3 mr-1" />
                                  First Score
                                </Badge>
                              )}
                              {flight.tripScore!.previousScore &&
                                flight.tripScore!.previousScore >
                                  flight.tripScore!.score && (
                                  <div className="flex items-center gap-1 mt-1 text-xs text-red-600">
                                    <TrendingDown className="h-3 w-3" />
                                    Down from {flight.tripScore!.previousScore}
                                  </div>
                                )}
                            </div>
                          </div>

                          <div className="space-y-2 text-xs">
                            <div className="flex justify-between">
                              <span className="text-muted-foreground">
                                On-Time Performance
                              </span>
                              <span className="font-medium">
                                {flight.tripScore!.factors.onTimePerformance}%
                              </span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-muted-foreground">
                                Aircraft Condition
                              </span>
                              <span className="font-medium">
                                {flight.tripScore!.factors.aircraftCondition}%
                              </span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-muted-foreground">
                                Crew Professionalism
                              </span>
                              <span className="font-medium">
                                {flight.tripScore!.factors.crewProfessionalism}%
                              </span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-muted-foreground">
                                Client Satisfaction
                              </span>
                              <span className="font-medium">
                                {flight.tripScore!.factors.clientSatisfaction}%
                              </span>
                            </div>
                          </div>
                        </div>
                      )}

                      {/* Operator Info */}
                      <div>
                        <p className="text-xs text-muted-foreground mb-2">
                          Operator
                        </p>
                        <p className="font-semibold">
                          {flight.aircraft.operator.name}
                        </p>
                        <p className="text-sm text-muted-foreground">
                          {flight.aircraft.operator.baseLocation}
                        </p>
                        <div className="flex gap-2 mt-2">
                          <Badge variant="secondary" className="text-xs">
                            ARGUS {flight.aircraft.operator.argusRating}
                          </Badge>
                          <Badge variant="secondary" className="text-xs">
                            Wyvern {flight.aircraft.operator.wyvernRating}
                          </Badge>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* AOG Alert & Actions */}
                  <div className="flex items-center justify-between pt-4 border-t gap-4">
                    <div className="flex-1">
                      {flight.hasAOG && (
                        <Alert className="border-red-200 bg-red-50">
                          <AlertTriangle className="h-4 w-4 text-red-600" />
                          <AlertTitle className="text-sm text-red-900">
                            AOG Incident Reported
                          </AlertTitle>
                          <AlertDescription className="text-sm text-red-800">
                            This aircraft is currently grounded.{' '}
                            {flight.status === 'under-maintenance' &&
                              'Under maintenance.'}
                          </AlertDescription>
                        </Alert>
                      )}
                    </div>

                    <div className="flex gap-2">
                      {flight.hasAOG && flight.aogReportId && (
                        <>
                          <Button
                            variant="destructive"
                            onClick={() =>
                              onViewAOGReport?.(flight.id, flight.aogReportId!)
                            }
                          >
                            <AlertTriangle className="h-4 w-4 mr-2" />
                            View AOG Report
                          </Button>
                          <Button
                            variant="outline"
                            onClick={() => onFindReplacement?.(flight)}
                          >
                            <Search className="h-4 w-4 mr-2" />
                            Find Replacement
                          </Button>
                        </>
                      )}
                      {!flight.hasAOG && (
                        <Button variant="outline" size="sm">
                          View Details
                        </Button>
                      )}
                    </div>
                  </div>
                </div>
              </Card>
            );
          })
        )}
      </div>
    </div>
  );
}
