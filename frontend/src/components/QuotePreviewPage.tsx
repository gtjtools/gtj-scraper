import { Button } from './ui/button';
import { Card } from './ui/card';
import { Badge } from './ui/badge';
import { Separator } from './ui/separator';
import { 
  ArrowLeft, 
  Send,
  MapPin, 
  Calendar, 
  Users, 
  Plane,
  Shield,
  Download,
  FileText,
  CheckCircle2
} from 'lucide-react';
import { QuoteFormData } from './CreateQuotePage';
import { ImageWithFallback } from './figma/ImageWithFallback';
import { TrustScoreGauge } from './TrustScoreGauge';
import { Aircraft } from '../lib/mock-data';

interface QuotePreviewPageProps {
  quoteData: QuoteFormData;
  onBack: () => void;
  onSend: () => void;
  onBookFlight: (aircraft: Aircraft, pricing: { operatorPrice: number; myPrice: number }) => void;
}

export function QuotePreviewPage({ quoteData, onBack, onSend, onBookFlight }: QuotePreviewPageProps) {
  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0
    }).format(amount);
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      weekday: 'long',
      year: 'numeric',
      month: 'long',
      day: 'numeric'
    });
  };

  const getRouteInfo = () => {
    if (quoteData.tripType === 'multi-leg' && quoteData.legs) {
      return {
        departure: quoteData.legs[0]?.departure || 'TBD',
        arrival: quoteData.legs[quoteData.legs.length - 1]?.arrival || 'TBD',
        date: quoteData.legs[0]?.date || new Date().toISOString()
      };
    }
    return {
      departure: quoteData.departure || 'TBD',
      arrival: quoteData.arrival || 'TBD',
      date: quoteData.departureDate || new Date().toISOString()
    };
  };

  const route = getRouteInfo();
  const passengers = quoteData.tripType === 'multi-leg' 
    ? (quoteData.legs?.[0]?.passengers || 6) 
    : (quoteData.passengers || 6);

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button
            variant="outline"
            onClick={onBack}
            className="gap-2"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Edit
          </Button>
          <div>
            <h1 className="text-3xl font-bold">{quoteData.title || 'Flight Quote Preview'}</h1>
            <p className="text-muted-foreground mt-1">
              Quote for {quoteData.client.name}
            </p>
          </div>
        </div>
        <Button
          onClick={onSend}
          className="bg-[#335cff] hover:bg-[#2847cc] gap-2 h-12 px-6"
        >
          <Send className="h-4 w-4" />
          Send to Client
        </Button>
      </div>

      {/* Quote Details Card */}
      <Card className="p-6">
        <div className="space-y-4">
          <div className="flex items-start justify-between">
            <div>
              <h2 className="font-bold mb-2">Trip Details</h2>
              {quoteData.message && (
                <p className="text-sm text-muted-foreground max-w-2xl">
                  {quoteData.message}
                </p>
              )}
            </div>
            {quoteData.expiresAt && (
              <Badge variant="outline" className="gap-1">
                <Calendar className="h-3 w-3" />
                Expires {new Date(quoteData.expiresAt).toLocaleDateString()}
              </Badge>
            )}
          </div>

          <Separator />

          <div className="grid md:grid-cols-3 gap-4">
            <div className="flex items-start gap-3">
              <MapPin className="h-5 w-5 text-muted-foreground mt-0.5 flex-shrink-0" />
              <div>
                <p className="text-sm text-muted-foreground">Route</p>
                <p className="font-semibold">{route.departure} → {route.arrival}</p>
              </div>
            </div>

            <div className="flex items-start gap-3">
              <Calendar className="h-5 w-5 text-muted-foreground mt-0.5 flex-shrink-0" />
              <div>
                <p className="text-sm text-muted-foreground">Date</p>
                <p className="font-semibold">{formatDate(route.date)}</p>
              </div>
            </div>

            <div className="flex items-start gap-3">
              <Users className="h-5 w-5 text-muted-foreground mt-0.5 flex-shrink-0" />
              <div>
                <p className="text-sm text-muted-foreground">Passengers</p>
                <p className="font-semibold">{passengers} passengers</p>
              </div>
            </div>
          </div>
        </div>
      </Card>

      {/* Aircraft Options */}
      <div className="space-y-4">
        <h2 className="font-bold">Available Aircraft</h2>
        
        {quoteData.aircraftPricing.map((option, index) => {
          const aircraft = option.aircraft;
          
          return (
            <Card key={aircraft.id} className="overflow-hidden">
              <div className="grid md:grid-cols-3 gap-6 p-6">
                {/* Aircraft Image */}
                <div className="md:col-span-1">
                  <div className="relative aspect-video rounded-lg overflow-hidden bg-slate-100">
                    <ImageWithFallback
                      src={aircraft.imageUrl}
                      alt={`${aircraft.manufacturer} ${aircraft.model}`}
                      className="w-full h-full object-cover"
                    />
                  </div>
                  <div className="mt-4 flex items-center gap-2">
                    <TrustScoreGauge 
                      score={aircraft.operator.trustScore} 
                      size="sm"
                    />
                    <div>
                      <p className="text-xs text-muted-foreground">TrustScore</p>
                      <p className="font-semibold">{aircraft.operator.trustScore}/100</p>
                    </div>
                  </div>
                </div>

                {/* Aircraft Details */}
                <div className="md:col-span-2 space-y-4">
                  {/* Header */}
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="text-xl font-bold">
                        {aircraft.manufacturer} {aircraft.model}
                      </h3>
                      <p className="text-sm text-muted-foreground">
                        Tail: {aircraft.tailNumber} • Operated by {aircraft.operator.name}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-2xl font-bold text-[#335cff]">
                        {formatCurrency(option.myPrice)}
                      </p>
                      <p className="text-xs text-muted-foreground">Total Price</p>
                    </div>
                  </div>

                  {/* Certifications */}
                  <div className="flex flex-wrap gap-2">
                    {aircraft.operator.argusRating && (
                      <Badge variant="outline" className="gap-1">
                        <Shield className="h-3 w-3" />
                        ARGUS {aircraft.operator.argusRating}
                      </Badge>
                    )}
                    {aircraft.operator.wyvernRating && (
                      <Badge variant="outline" className="gap-1">
                        <Shield className="h-3 w-3" />
                        Wyvern {aircraft.operator.wyvernRating}
                      </Badge>
                    )}
                    {aircraft.operator.aogIncidents === 0 && (
                      <Badge variant="outline" className="gap-1 bg-green-100 text-green-800">
                        <CheckCircle2 className="h-3 w-3" />
                        No AOG
                      </Badge>
                    )}
                  </div>

                  {/* About */}
                  <div>
                    <h4 className="font-semibold mb-2">About This Aircraft</h4>
                    <p className="text-sm text-muted-foreground">
                      This {aircraft.manufacturer} {aircraft.model} offers exceptional comfort and performance 
                      for your journey. With a range of {aircraft.range.toLocaleString()} nautical miles and 
                      seating for up to {aircraft.capacity} passengers, it's perfect for your {route.departure} to {route.arrival} flight.
                    </p>
                  </div>

                  {/* Amenities */}
                  {aircraft.amenities && aircraft.amenities.length > 0 && (
                    <div>
                      <h4 className="font-semibold mb-2">Amenities</h4>
                      <div className="flex flex-wrap gap-2">
                        {aircraft.amenities.map((amenity, idx) => (
                          <Badge key={idx} variant="secondary">
                            <CheckCircle2 className="h-3 w-3 mr-1" />
                            {amenity}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Action Buttons */}
                  <div className="flex gap-3 pt-4 border-t">
                    <Button variant="outline" className="gap-2 flex-1">
                      <Download className="h-4 w-4" />
                      Download PDF
                    </Button>
                    <Button variant="outline" className="gap-2 flex-1">
                      <FileText className="h-4 w-4" />
                      Review Contract
                    </Button>
                    <Button 
                      onClick={() => onBookFlight(aircraft, { 
                        operatorPrice: option.operatorPrice, 
                        myPrice: option.myPrice 
                      })}
                      className="bg-[#335cff] hover:bg-[#2847cc] gap-2 flex-1"
                    >
                      <Plane className="h-4 w-4" />
                      Book This Flight
                    </Button>
                  </div>
                </div>
              </div>
            </Card>
          );
        })}
      </div>

      {/* Footer Note */}
      <Card className="p-4 bg-muted/50">
        <p className="text-sm text-muted-foreground text-center">
          This quote is valid until {quoteData.expiresAt ? formatDate(quoteData.expiresAt) : 'the specified expiration date'}. 
          Prices are subject to availability and may change.
        </p>
      </Card>
    </div>
  );
}