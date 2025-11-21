import { Aircraft, SearchCriteria } from '../lib/mock-data';
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from './ui/sheet';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { TrustScoreGauge } from './TrustScoreGauge';
import { ScrollArea } from './ui/scroll-area';
import { Separator } from './ui/separator';
import { X, Plane, Users, FileText } from 'lucide-react';
import { Card } from './ui/card';

interface ShortlistSheetProps {
  isOpen: boolean;
  onClose: () => void;
  shortlistedAircraft: Aircraft[];
  onRemove: (aircraftId: string) => void;
  onGenerateQuote: () => void;
  searchCriteria: SearchCriteria | null;
}

export function ShortlistSheet({
  isOpen,
  onClose,
  shortlistedAircraft,
  onRemove,
  onGenerateQuote,
  searchCriteria
}: ShortlistSheetProps) {
  const totalCost = shortlistedAircraft.reduce((sum, aircraft) => {
    // Calculate estimated cost based on search criteria if available
    const flightTime = searchCriteria ? 3 : 3; // Default to 3 hours
    return sum + (aircraft.hourlyRate * flightTime);
  }, 0);

  return (
    <Sheet open={isOpen} onOpenChange={onClose}>
      <SheetContent side="left" className="w-full sm:max-w-lg p-0 flex flex-col">
        <SheetHeader className="border-b px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              <SheetTitle>Shortlisted Flights</SheetTitle>
              <SheetDescription>
                {shortlistedAircraft.length} {shortlistedAircraft.length === 1 ? 'option' : 'options'} selected
              </SheetDescription>
            </div>
            {shortlistedAircraft.length > 0 && (
              <Badge className="bg-[#335cff]">
                {shortlistedAircraft.length}
              </Badge>
            )}
          </div>
        </SheetHeader>

        <ScrollArea className="flex-1 px-6">
          {shortlistedAircraft.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <div className="w-16 h-16 rounded-full bg-muted flex items-center justify-center mb-4">
                <Plane className="h-8 w-8 text-muted-foreground" />
              </div>
              <h3 className="font-semibold mb-2">No flights shortlisted</h3>
              <p className="text-sm text-muted-foreground max-w-sm">
                Search for aircraft and add them to your shortlist, then generate a quote to present options to your client.
              </p>
            </div>
          ) : (
            <div className="space-y-4 py-4">
              {/* Search Criteria Summary */}
              {searchCriteria && (
                <Card className="p-4 bg-muted/30">
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <div className="flex items-center gap-2">
                      <Plane className="h-4 w-4 text-muted-foreground" />
                      <div>
                        <p className="text-xs text-muted-foreground">Route</p>
                        <p className="font-medium">
                          {searchCriteria.departure} → {searchCriteria.arrival}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Users className="h-4 w-4 text-muted-foreground" />
                      <div>
                        <p className="text-xs text-muted-foreground">Passengers</p>
                        <p className="font-medium">{searchCriteria.passengers}</p>
                      </div>
                    </div>
                  </div>
                </Card>
              )}

              {/* Shortlisted Aircraft */}
              {shortlistedAircraft.map((aircraft) => (
                <Card key={aircraft.id} className="p-4">
                  <div className="flex items-start gap-4">
                    <div className="flex-shrink-0">
                      <TrustScoreGauge score={aircraft.operator.trustScore} size="sm" />
                    </div>
                    
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-2 mb-2">
                        <div>
                          <h4 className="font-semibold">
                            {aircraft.manufacturer} {aircraft.model}
                          </h4>
                          <p className="text-sm text-muted-foreground">
                            {aircraft.operator.name}
                          </p>
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => onRemove(aircraft.id)}
                          className="h-8 w-8 p-0"
                        >
                          <X className="h-4 w-4" />
                        </Button>
                      </div>

                      <div className="space-y-2">
                        <div className="flex items-center gap-4 text-sm">
                          <div>
                            <span className="text-muted-foreground">Type: </span>
                            <span className="font-medium">{aircraft.type}</span>
                          </div>
                          <div>
                            <span className="text-muted-foreground">Capacity: </span>
                            <span className="font-medium">{aircraft.capacity} pax</span>
                          </div>
                        </div>

                        <div className="flex items-center justify-between">
                          <div className="flex gap-2">
                            {aircraft.operator.certifications.slice(0, 2).map((cert, i) => (
                              <Badge key={i} variant="secondary" className="text-xs">
                                {cert}
                              </Badge>
                            ))}
                          </div>
                          <p className="font-semibold text-[#335cff]">
                            ${aircraft.hourlyRate.toLocaleString()}/hr
                          </p>
                        </div>
                      </div>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </ScrollArea>

        {shortlistedAircraft.length > 0 && (
          <>
            <Separator />
            <div className="p-6 space-y-4">
              {/* Total Estimate */}
              <div className="bg-muted/30 rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm text-muted-foreground">Estimated Total</span>
                  <span className="text-sm text-muted-foreground">
                    (3 hours flight time)
                  </span>
                </div>
                <p className="text-2xl font-bold text-[#335cff]">
                  ${totalCost.toLocaleString()}
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  Average across {shortlistedAircraft.length} {shortlistedAircraft.length === 1 ? 'option' : 'options'}
                </p>
              </div>

              {/* Actions */}
              <div className="space-y-2">
                <Button
                  onClick={onGenerateQuote}
                  className="w-full bg-[#335cff] hover:bg-[#2847cc] gap-2"
                >
                  <FileText className="h-4 w-4" />
                  Generate Quote
                </Button>
                <Button
                  onClick={onClose}
                  variant="outline"
                  className="w-full"
                >
                  Continue Browsing
                </Button>
              </div>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
