import { Aircraft } from '../lib/mock-data';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from './ui/dialog';
import { TrustScoreGauge } from './TrustScoreGauge';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Separator } from './ui/separator';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import { Building2, Shield, FileText, AlertTriangle, Plus, Check, Star, Clock, MapPin, User } from 'lucide-react';

interface AircraftDetailsModalProps {
  aircraft: Aircraft | null;
  isOpen: boolean;
  onClose: () => void;
  onAddToShortlist?: (aircraft: Aircraft) => void;
  isShortlisted?: boolean;
}

export function AircraftDetailsModal({ aircraft, isOpen, onClose, onAddToShortlist, isShortlisted = false }: AircraftDetailsModalProps) {
  if (!aircraft) return null;

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-3xl max-h-[90vh] overflow-hidden flex flex-col">
        <DialogHeader className="shrink-0">
          <div className="flex items-start justify-between gap-4">
            <div>
              <DialogTitle>
                {aircraft.manufacturer} {aircraft.model}
              </DialogTitle>
              <DialogDescription>
                {aircraft.tailNumber}
              </DialogDescription>
            </div>
            {onAddToShortlist && (
              <Button
                onClick={() => onAddToShortlist(aircraft)}
                className={isShortlisted ? 'bg-green-600 hover:bg-green-700' : 'bg-[#335cff] hover:bg-[#2847cc]'}
                disabled={aircraft.availability === 'unavailable'}
              >
                {isShortlisted ? (
                  <>
                    <Check className="h-4 w-4 mr-2" />
                    Shortlisted
                  </>
                ) : (
                  <>
                    <Plus className="h-4 w-4 mr-2" />
                    Add to Shortlist
                  </>
                )}
              </Button>
            )}
          </div>
        </DialogHeader>

        {/* Scrollable content area */}
        <div className="overflow-y-auto flex-1 -mx-6 px-6">
          {/* Operator Summary - Prominent at the top */}
          <div className="bg-gradient-to-br from-slate-50 to-slate-100 rounded-xl p-6 border border-slate-200">
          <div className="flex items-start gap-6">
            <div className="flex-shrink-0">
              <TrustScoreGauge score={aircraft.operator.trustScore} size="lg" />
            </div>
            
            <div className="flex-1 space-y-4">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <Building2 className="h-4 w-4 text-muted-foreground" />
                  <h3 className="font-semibold">Operator</h3>
                </div>
                <p className="text-lg font-bold">{aircraft.operator.name}</p>
                <p className="text-sm text-muted-foreground">{aircraft.operator.baseLocation}</p>
              </div>

              <div className="grid grid-cols-3 gap-4">
                <div className="flex items-start gap-2">
                  <Shield className="h-4 w-4 text-green-600 mt-0.5 flex-shrink-0" />
                  <div>
                    <p className="text-xs text-muted-foreground">ARGUS</p>
                    <p className="font-semibold text-sm">{aircraft.operator.argusRating}</p>
                  </div>
                </div>
                <div className="flex items-start gap-2">
                  <Shield className="h-4 w-4 text-blue-600 mt-0.5 flex-shrink-0" />
                  <div>
                    <p className="text-xs text-muted-foreground">Wyvern</p>
                    <p className="font-semibold text-sm">{aircraft.operator.wyvernRating}</p>
                  </div>
                </div>
                <div className="flex items-start gap-2">
                  <AlertTriangle className={`h-4 w-4 mt-0.5 flex-shrink-0 ${aircraft.operator.aogIncidents === 0 ? 'text-green-600' : 'text-amber-600'}`} />
                  <div>
                    <p className="text-xs text-muted-foreground">AOG (12mo)</p>
                    <p className="font-semibold text-sm">{aircraft.operator.aogIncidents}</p>
                  </div>
                </div>
              </div>

              <div className="flex gap-2 flex-wrap">
                {aircraft.operator.certifications.map((cert, i) => (
                  <Badge key={i} variant="secondary" className="text-xs">
                    {cert}
                  </Badge>
                ))}
              </div>
            </div>
          </div>
        </div>

        <Tabs defaultValue="aircraft" className="w-full">
          <TabsList className="grid w-full grid-cols-5">
            <TabsTrigger value="aircraft">Aircraft</TabsTrigger>
            <TabsTrigger value="operator">Operator</TabsTrigger>
            <TabsTrigger value="safety">Safety</TabsTrigger>
            <TabsTrigger value="aog" className="gap-1">
              AOGs
              {aircraft.aogIncidents && aircraft.aogIncidents.length > 0 && (
                <Badge variant="secondary" className="ml-1 h-5 px-1.5 text-xs">
                  {aircraft.aogIncidents.length}
                </Badge>
              )}
            </TabsTrigger>
            <TabsTrigger value="trips" className="gap-1">
              Trips
              {aircraft.tripReports && aircraft.tripReports.length > 0 && (
                <Badge variant="secondary" className="ml-1 h-5 px-1.5 text-xs">
                  {aircraft.tripReports.length}
                </Badge>
              )}
            </TabsTrigger>
          </TabsList>

          <TabsContent value="aircraft" className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">Type</p>
                <p className="font-medium">{aircraft.type}</p>
              </div>
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">Year</p>
                <p className="font-medium">{aircraft.year}</p>
              </div>
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">Capacity</p>
                <p className="font-medium">{aircraft.capacity} passengers</p>
              </div>
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">Range</p>
                <p className="font-medium">{aircraft.range.toLocaleString()} nautical miles</p>
              </div>
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">Hourly Rate</p>
                <p className="font-medium">${aircraft.hourlyRate.toLocaleString()}/hr</p>
              </div>
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground">Availability</p>
                <Badge variant="outline" className="capitalize">{aircraft.availability}</Badge>
              </div>
            </div>

            <Separator />

            <div className="space-y-2">
              <h4 className="font-semibold">Aircraft Features</h4>
              <ul className="grid grid-cols-2 gap-2 text-sm">
                <li className="flex items-center gap-2">
                  <div className="h-1.5 w-1.5 rounded-full bg-[#335cff]" />
                  WiFi Connectivity
                </li>
                <li className="flex items-center gap-2">
                  <div className="h-1.5 w-1.5 rounded-full bg-[#335cff]" />
                  Full Galley
                </li>
                <li className="flex items-center gap-2">
                  <div className="h-1.5 w-1.5 rounded-full bg-[#335cff]" />
                  Entertainment System
                </li>
                <li className="flex items-center gap-2">
                  <div className="h-1.5 w-1.5 rounded-full bg-[#335cff]" />
                  Private Lavatory
                </li>
                <li className="flex items-center gap-2">
                  <div className="h-1.5 w-1.5 rounded-full bg-[#335cff]" />
                  Enclosed Baggage
                </li>
                <li className="flex items-center gap-2">
                  <div className="h-1.5 w-1.5 rounded-full bg-[#335cff]" />
                  Satellite Phone
                </li>
              </ul>
            </div>
          </TabsContent>

          <TabsContent value="operator" className="space-y-4">
            <div className="flex items-start gap-6">
              <TrustScoreGauge score={aircraft.operator.trustScore} size="lg" />
              <div className="flex-1 space-y-3">
                <div>
                  <h4 className="font-semibold mb-1">{aircraft.operator.name}</h4>
                  <p className="text-sm text-muted-foreground">{aircraft.operator.baseLocation}</p>
                </div>
                <div className="flex gap-2 flex-wrap">
                  {aircraft.operator.certifications.map((cert, i) => (
                    <Badge key={i} variant="secondary" className="text-xs">
                      {cert}
                    </Badge>
                  ))}
                </div>
              </div>
            </div>

            <Separator />

            <div className="grid grid-cols-2 gap-4">
              <div className="flex items-start gap-3">
                <Building2 className="h-5 w-5 text-muted-foreground mt-1" />
                <div>
                  <p className="text-sm text-muted-foreground">Fleet Size</p>
                  <p className="font-semibold">{aircraft.operator.fleetSize} aircraft</p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <Shield className="h-5 w-5 text-muted-foreground mt-1" />
                <div>
                  <p className="text-sm text-muted-foreground">ARGUS Rating</p>
                  <p className="font-semibold">{aircraft.operator.argusRating}</p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <FileText className="h-5 w-5 text-muted-foreground mt-1" />
                <div>
                  <p className="text-sm text-muted-foreground">Wyvern Rating</p>
                  <p className="font-semibold">{aircraft.operator.wyvernRating}</p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <AlertTriangle className="h-5 w-5 text-muted-foreground mt-1" />
                <div>
                  <p className="text-sm text-muted-foreground">AOG Incidents (12mo)</p>
                  <p className="font-semibold">{aircraft.operator.aogIncidents}</p>
                </div>
              </div>
            </div>
          </TabsContent>

          <TabsContent value="safety" className="space-y-4">
            <div className="space-y-3">
              <div className="flex items-center justify-between p-3 bg-green-50 rounded-lg border border-green-200">
                <div className="flex items-center gap-3">
                  <Shield className="h-5 w-5 text-green-600" />
                  <div>
                    <p className="font-semibold text-green-900">ARGUS Platinum Rated</p>
                    <p className="text-sm text-green-700">Highest safety certification</p>
                  </div>
                </div>
                <Badge className="bg-green-600">Verified</Badge>
              </div>

              <div className="flex items-center justify-between p-3 bg-blue-50 rounded-lg border border-blue-200">
                <div className="flex items-center gap-3">
                  <Shield className="h-5 w-5 text-blue-600" />
                  <div>
                    <p className="font-semibold text-blue-900">Wyvern Wingman</p>
                    <p className="text-sm text-blue-700">Advanced safety audit passed</p>
                  </div>
                </div>
                <Badge className="bg-blue-600">Verified</Badge>
              </div>

              {aircraft.operator.aogIncidents === 0 ? (
                <div className="flex items-center justify-between p-3 bg-green-50 rounded-lg border border-green-200">
                  <div className="flex items-center gap-3">
                    <AlertTriangle className="h-5 w-5 text-green-600" />
                    <div>
                      <p className="font-semibold text-green-900">No AOG Incidents</p>
                      <p className="text-sm text-green-700">Perfect record in past 12 months</p>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="flex items-center justify-between p-3 bg-amber-50 rounded-lg border border-amber-200">
                  <div className="flex items-center gap-3">
                    <AlertTriangle className="h-5 w-5 text-amber-600" />
                    <div>
                      <p className="font-semibold text-amber-900">{aircraft.operator.aogIncidents} AOG Incident(s)</p>
                      <p className="text-sm text-amber-700">Reported in past 12 months</p>
                    </div>
                  </div>
                </div>
              )}
            </div>

            <Separator />

            <div className="space-y-2">
              <h4 className="font-semibold">Insurance Coverage</h4>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Liability Coverage</span>
                  <span className="font-medium">$500M</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Hull Coverage</span>
                  <span className="font-medium">Full Value</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">War Risk</span>
                  <span className="font-medium">Included</span>
                </div>
              </div>
            </div>
          </TabsContent>

          {/* AOG Incidents Tab */}
          <TabsContent value="aog" className="space-y-4">
            {aircraft.aogIncidents && aircraft.aogIncidents.length > 0 ? (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h4 className="font-semibold">AOG Incident History</h4>
                  <Badge variant="outline">
                    {aircraft.aogIncidents.length} incident{aircraft.aogIncidents.length !== 1 ? 's' : ''} (12 months)
                  </Badge>
                </div>
                
                <div className="space-y-3">
                  {aircraft.aogIncidents.map((incident) => {
                    const severityColors = {
                      minor: 'bg-blue-50 border-blue-200',
                      moderate: 'bg-amber-50 border-amber-200',
                      major: 'bg-red-50 border-red-200'
                    };
                    
                    const severityBadgeColors = {
                      minor: 'bg-blue-600',
                      moderate: 'bg-amber-600',
                      major: 'bg-red-600'
                    };

                    return (
                      <div
                        key={incident.id}
                        className={`p-4 rounded-lg border ${severityColors[incident.severity]}`}
                      >
                        <div className="flex items-start justify-between gap-4 mb-3">
                          <div className="flex items-start gap-3 flex-1">
                            <AlertTriangle className="h-5 w-5 text-amber-600 mt-0.5 flex-shrink-0" />
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 mb-1 flex-wrap">
                                <p className="font-semibold">{incident.description}</p>
                                <Badge className={`${severityBadgeColors[incident.severity]} capitalize`}>
                                  {incident.severity}
                                </Badge>
                              </div>
                              <div className="flex items-center gap-3 text-sm text-muted-foreground flex-wrap">
                                <span className="flex items-center gap-1">
                                  <Clock className="h-3 w-3" />
                                  {new Date(incident.date).toLocaleDateString('en-US', { 
                                    month: 'short', 
                                    day: 'numeric', 
                                    year: 'numeric' 
                                  })}
                                </span>
                                <span className="flex items-center gap-1">
                                  <MapPin className="h-3 w-3" />
                                  {incident.location}
                                </span>
                                <span>Downtime: {incident.downtime}</span>
                              </div>
                            </div>
                          </div>
                        </div>
                        
                        <div className="ml-8 space-y-2">
                          <div>
                            <p className="text-xs font-medium text-muted-foreground mb-1">Resolution</p>
                            <p className="text-sm">{incident.resolution}</p>
                          </div>
                          
                          <div className="flex items-center gap-2">
                            <Badge 
                              variant={incident.status === 'resolved' ? 'default' : 'secondary'}
                              className={incident.status === 'resolved' ? 'bg-green-600' : ''}
                            >
                              {incident.status === 'resolved' ? (
                                <>
                                  <Check className="h-3 w-3 mr-1" />
                                  Resolved
                                </>
                              ) : (
                                'Pending'
                              )}
                            </Badge>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-12 text-center">
                <div className="rounded-full bg-green-100 p-4 mb-4">
                  <Check className="h-8 w-8 text-green-600" />
                </div>
                <h4 className="font-semibold mb-2">No AOG Incidents</h4>
                <p className="text-sm text-muted-foreground max-w-sm">
                  This aircraft has a perfect record with no Aircraft on Ground incidents in the past 12 months.
                </p>
              </div>
            )}
          </TabsContent>

          {/* Trip Reports Tab */}
          <TabsContent value="trips" className="space-y-4">
            {aircraft.tripReports && aircraft.tripReports.length > 0 ? (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h4 className="font-semibold">Recent Trip Reports</h4>
                  <Badge variant="outline">
                    {aircraft.tripReports.length} trip{aircraft.tripReports.length !== 1 ? 's' : ''}
                  </Badge>
                </div>
                
                <div className="space-y-3">
                  {aircraft.tripReports.map((trip) => {
                    const performanceColors = {
                      'on-time': 'bg-green-50 border-green-200',
                      'early': 'bg-blue-50 border-blue-200',
                      'delayed': 'bg-amber-50 border-amber-200'
                    };
                    
                    const performanceBadgeColors = {
                      'on-time': 'bg-green-600',
                      'early': 'bg-blue-600',
                      'delayed': 'bg-amber-600'
                    };

                    const performanceLabels = {
                      'on-time': 'On Time',
                      'early': 'Early Arrival',
                      'delayed': 'Delayed'
                    };

                    return (
                      <div
                        key={trip.id}
                        className={`p-4 rounded-lg border ${performanceColors[trip.onTimePerformance]}`}
                      >
                        <div className="flex items-start justify-between gap-4 mb-3">
                          <div className="flex-1">
                            <div className="flex items-center gap-2 mb-2 flex-wrap">
                              <p className="font-semibold">{trip.route}</p>
                              <Badge className={performanceBadgeColors[trip.onTimePerformance]}>
                                {performanceLabels[trip.onTimePerformance]}
                              </Badge>
                              <div className="flex items-center gap-1">
                                {[...Array(5)].map((_, i) => (
                                  <Star
                                    key={i}
                                    className={`h-3.5 w-3.5 ${
                                      i < trip.rating
                                        ? 'fill-yellow-400 text-yellow-400'
                                        : 'text-gray-300'
                                    }`}
                                  />
                                ))}
                                <span className="text-sm font-medium ml-1">{trip.rating}.0</span>
                              </div>
                            </div>
                            
                            <div className="grid grid-cols-2 gap-2 text-sm text-muted-foreground mb-3">
                              <span className="flex items-center gap-1">
                                <Clock className="h-3 w-3" />
                                {new Date(trip.date).toLocaleDateString('en-US', { 
                                  month: 'short', 
                                  day: 'numeric', 
                                  year: 'numeric' 
                                })}
                              </span>
                              <span className="flex items-center gap-1">
                                <User className="h-3 w-3" />
                                {trip.client}
                              </span>
                              <span className="flex items-center gap-1">
                                <Shield className="h-3 w-3" />
                                {trip.pilot}
                              </span>
                              <span>Flight Time: {trip.flightTime}</span>
                            </div>
                            
                            <div className="bg-white/70 rounded-md p-3 border border-border/50">
                              <p className="text-xs font-medium text-muted-foreground mb-1">Client Feedback</p>
                              <p className="text-sm italic">"{trip.feedback}"</p>
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>

                {/* Summary Stats */}
                <Separator />
                <div className="grid grid-cols-3 gap-4">
                  <div className="text-center">
                    <p className="text-2xl font-bold">
                      {(aircraft.tripReports.reduce((acc, t) => acc + t.rating, 0) / aircraft.tripReports.length).toFixed(1)}
                    </p>
                    <p className="text-sm text-muted-foreground">Avg Rating</p>
                  </div>
                  <div className="text-center">
                    <p className="text-2xl font-bold">
                      {Math.round((aircraft.tripReports.filter(t => t.onTimePerformance !== 'delayed').length / aircraft.tripReports.length) * 100)}%
                    </p>
                    <p className="text-sm text-muted-foreground">On-Time Rate</p>
                  </div>
                  <div className="text-center">
                    <p className="text-2xl font-bold">
                      {aircraft.tripReports.length}
                    </p>
                    <p className="text-sm text-muted-foreground">Total Trips</p>
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-12 text-center">
                <div className="rounded-full bg-slate-100 p-4 mb-4">
                  <FileText className="h-8 w-8 text-muted-foreground" />
                </div>
                <h4 className="font-semibold mb-2">No Trip Reports</h4>
                <p className="text-sm text-muted-foreground max-w-sm">
                  No trip reports are available for this aircraft yet.
                </p>
              </div>
            )}
          </TabsContent>
        </Tabs>
        </div>
      </DialogContent>
    </Dialog>
  );
}
