import { useState } from 'react';
import { ArrowLeft, Plus, Save, Send, User, MapPin, Calendar, Users, Plane, X, FileText, DollarSign } from 'lucide-react';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Card } from './ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Textarea } from './ui/textarea';
import { Checkbox } from './ui/checkbox';
import { Badge } from './ui/badge';
import { TrustScoreGauge } from './TrustScoreGauge';
import { Aircraft, Client, AircraftQuoteOption } from '../lib/mock-data';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from './ui/dialog';

interface CreateQuotePageProps {
  shortlistedAircraft: Aircraft[];
  existingClients: Client[];
  onSaveDraft: (quoteData: QuoteFormData) => void;
  onPreviewQuote: (quoteData: QuoteFormData) => void;
  onCancel: () => void;
  onSaveClient: (client: Omit<Client, 'id'>) => Client;
  onViewAircraftDetails: (aircraft: Aircraft) => void;
}

export interface FlightLeg {
  departure: string;
  arrival: string;
  date: string;
  passengers: number;
  notes?: string;
}

export interface QuoteFormData {
  client: Client;
  tripType: 'one-way' | 'round-trip' | 'multi-leg';
  // For one-way and round-trip (all optional with defaults)
  departure?: string;
  arrival?: string;
  departureDate?: string;
  returnDate?: string;
  passengers?: number;
  notes?: string;
  // For multi-leg
  legs?: FlightLeg[];
  // Quote settings (all optional with defaults)
  title?: string;
  message?: string;
  expiresAt?: string;
  status?: 'draft' | 'sent';
  // Aircraft pricing
  aircraftPricing: AircraftQuoteOption[];
}

export function CreateQuotePage({
  shortlistedAircraft,
  existingClients,
  onSaveDraft,
  onPreviewQuote,
  onCancel,
  onSaveClient,
  onViewAircraftDetails
}: CreateQuotePageProps) {
  const [clientMode, setClientMode] = useState<'existing' | 'new'>('new');
  const [selectedClientId, setSelectedClientId] = useState<string>('');
  const [saveNewClient, setSaveNewClient] = useState(true);
  const [showSaveClientDialog, setShowSaveClientDialog] = useState(false);
  
  // New client form
  const [newClientName, setNewClientName] = useState('');
  const [newClientCompany, setNewClientCompany] = useState('');
  const [newClientEmail, setNewClientEmail] = useState('');
  const [newClientPhone, setNewClientPhone] = useState('');

  // Trip type
  const [tripType, setTripType] = useState<'one-way' | 'round-trip' | 'multi-leg'>('one-way');

  // Flight details (for one-way and round-trip)
  const [departure, setDeparture] = useState('');
  const [arrival, setArrival] = useState('');
  const [departureDate, setDepartureDate] = useState('');
  const [returnDate, setReturnDate] = useState('');
  const [passengers, setPassengers] = useState('');
  const [notes, setNotes] = useState('');

  // Multi-leg flight details
  const [legs, setLegs] = useState<FlightLeg[]>([
    { departure: '', arrival: '', date: '', passengers: 0, notes: '' }
  ]);

  // Quote settings
  const [quoteTitle, setQuoteTitle] = useState('');
  const [quoteMessage, setQuoteMessage] = useState('');
  const [expiresAt, setExpiresAt] = useState(() => {
    // Default to 7 days from now
    const date = new Date();
    date.setDate(date.getDate() + 7);
    return date.toISOString().split('T')[0];
  });

  // Aircraft pricing - initialize with operator's hourly rate (assuming 3hr flight)
  const [aircraftPricing, setAircraftPricing] = useState<Record<string, { operatorPrice: number; myPrice: number }>>(
    () => {
      const pricing: Record<string, { operatorPrice: number; myPrice: number }> = {};
      shortlistedAircraft.forEach(aircraft => {
        const basePrice = aircraft.hourlyRate * 3; // Assuming 3 hour flight
        pricing[aircraft.id] = {
          operatorPrice: basePrice,
          myPrice: Math.round(basePrice * 1.15) // Default 15% markup
        };
      });
      return pricing;
    }
  );

  const handleUpdateAircraftPricing = (aircraftId: string, field: 'operatorPrice' | 'myPrice', value: number) => {
    setAircraftPricing(prev => ({
      ...prev,
      [aircraftId]: {
        ...prev[aircraftId],
        [field]: value
      }
    }));
  };

  const handleSubmit = (action: 'draft' | 'preview') => {
    let client: Client;

    if (clientMode === 'new') {
      // Use defaults if fields are empty
      const hasClientData = newClientName || newClientEmail;
      
      if (saveNewClient && action === 'preview' && hasClientData) {
        // Show confirmation dialog before saving (only if they entered data)
        setShowSaveClientDialog(true);
        return;
      }
      
      // Create client with defaults
      client = {
        id: `temp-${Date.now()}`,
        name: newClientName || 'Client Name',
        company: newClientCompany || 'Company Name',
        email: newClientEmail || 'client@example.com',
        phone: newClientPhone || '+1 (555) 000-0000'
      };
    } else {
      const existingClient = existingClients.find(c => c.id === selectedClientId);
      if (!existingClient) {
        // Use first client as default or create temp client
        client = existingClients[0] || {
          id: `temp-${Date.now()}`,
          name: 'Client Name',
          company: 'Company Name',
          email: 'client@example.com',
          phone: '+1 (555) 000-0000'
        };
      } else {
        client = existingClient;
      }
    }

    submitQuote(client, action);
  };

  const handleSaveClientAndSubmit = (action: 'draft' | 'preview') => {
    const newClient = onSaveClient({
      name: newClientName,
      company: newClientCompany,
      email: newClientEmail,
      phone: newClientPhone
    });
    setShowSaveClientDialog(false);
    submitQuote(newClient, action);
  };

  const submitQuote = (client: Client, action: 'draft' | 'preview') => {
    // Build aircraft pricing array
    const pricingArray: AircraftQuoteOption[] = shortlistedAircraft.map(aircraft => ({
      aircraft,
      operatorPrice: aircraftPricing[aircraft.id]?.operatorPrice || 0,
      myPrice: aircraftPricing[aircraft.id]?.myPrice || 0
    }));

    // Use defaults for empty fields
    const defaultDate = new Date().toISOString().split('T')[0];
    const getNextWeek = () => {
      const date = new Date();
      date.setDate(date.getDate() + 7);
      return date.toISOString().split('T')[0];
    };

    const quoteData: QuoteFormData = {
      client,
      tripType,
      title: quoteTitle || `${client.name || 'Client'} Flight Quote`,
      message: quoteMessage || undefined,
      expiresAt: expiresAt ? new Date(expiresAt).toISOString() : undefined,
      aircraftPricing: pricingArray,
      ...(tripType === 'multi-leg' 
        ? { 
            legs: legs.length > 0 && legs[0].departure 
              ? legs 
              : [{ 
                  departure: 'TBD', 
                  arrival: 'TBD', 
                  date: defaultDate, 
                  passengers: 6, 
                  notes: '' 
                }] 
          }
        : {
            departure: departure || 'TBD',
            arrival: arrival || 'TBD',
            departureDate: departureDate || defaultDate,
            returnDate: returnDate || (tripType === 'round-trip' ? getNextWeek() : undefined),
            passengers: passengers ? parseInt(passengers) : 6,
            notes: notes || undefined
          }
      )
    };

    if (action === 'draft') {
      onSaveDraft(quoteData);
    } else {
      onPreviewQuote(quoteData);
    }
  };

  const handleAddLeg = () => {
    setLegs([...legs, { departure: '', arrival: '', date: '', passengers: 0, notes: '' }]);
  };

  const handleRemoveLeg = (index: number) => {
    if (legs.length > 1) {
      setLegs(legs.filter((_, i) => i !== index));
    }
  };

  const handleUpdateLeg = (index: number, field: keyof FlightLeg, value: string | number) => {
    const updatedLegs = legs.map((leg, i) => 
      i === index ? { ...leg, [field]: value } : leg
    );
    setLegs(updatedLegs);
  };

  // Always return true - we'll use defaults for empty fields
  const isFormValid = () => {
    return true;
  };

  return (
    <div className="max-w-5xl mx-auto">
      {/* Header */}
      <div className="mb-6">
        <Button
          variant="ghost"
          onClick={onCancel}
          className="mb-4 -ml-2"
        >
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back
        </Button>
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-3xl mb-2">Generate Quote</h1>
            <p className="text-muted-foreground">
              Create a quote with {shortlistedAircraft.length} aircraft option{shortlistedAircraft.length !== 1 ? 's' : ''} for your client
            </p>
          </div>
        </div>
      </div>

      <div className="space-y-6">
        {/* Client Information */}
        <Card className="p-6">
          <div className="flex items-center gap-2 mb-6">
            <User className="h-5 w-5 text-[#335cff]" />
            <h2>Client Information</h2>
          </div>

          {/* Client Mode Toggle */}
          <div className="inline-flex gap-1 mb-6 p-1 bg-muted rounded-lg">
            <button
              type="button"
              onClick={() => setClientMode('new')}
              className={`px-4 py-2 rounded-md transition-colors ${
                clientMode === 'new'
                  ? 'bg-background shadow-sm'
                  : 'hover:bg-background/50'
              }`}
            >
              New Client
            </button>
            <button
              type="button"
              onClick={() => setClientMode('existing')}
              className={`px-4 py-2 rounded-md transition-colors ${
                clientMode === 'existing'
                  ? 'bg-background shadow-sm'
                  : 'hover:bg-background/50'
              }`}
            >
              Existing Client
            </button>
          </div>

          {/* Existing Client Selection */}
          {clientMode === 'existing' && (
            <div className="space-y-2">
              <Label htmlFor="client-select">Select Client</Label>
              <Select value={selectedClientId} onValueChange={setSelectedClientId}>
                <SelectTrigger id="client-select" className="h-11 bg-input-background border-0">
                  <SelectValue placeholder="Choose a client..." />
                </SelectTrigger>
                <SelectContent>
                  {existingClients.map((client) => (
                    <SelectItem key={client.id} value={client.id}>
                      <div className="flex flex-col items-start">
                        <span>{client.name}</span>
                        <span className="text-xs text-muted-foreground">{client.company}</span>
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {/* New Client Form */}
          {clientMode === 'new' && (
            <div className="space-y-4">
              <div className="grid md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="client-name">Client Name</Label>
                  <Input
                    id="client-name"
                    placeholder="John Smith (or leave blank for default)"
                    value={newClientName}
                    onChange={(e) => setNewClientName(e.target.value)}
                    className="h-11 bg-input-background border-0"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="client-company">Company</Label>
                  <Input
                    id="client-company"
                    placeholder="Acme Corp"
                    value={newClientCompany}
                    onChange={(e) => setNewClientCompany(e.target.value)}
                    className="h-11 bg-input-background border-0"
                  />
                </div>
              </div>
              <div className="grid md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="client-email">Email</Label>
                  <Input
                    id="client-email"
                    type="email"
                    placeholder="john@example.com"
                    value={newClientEmail}
                    onChange={(e) => setNewClientEmail(e.target.value)}
                    className="h-11 bg-input-background border-0"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="client-phone">Phone</Label>
                  <Input
                    id="client-phone"
                    type="tel"
                    placeholder="+1 (555) 123-4567"
                    value={newClientPhone}
                    onChange={(e) => setNewClientPhone(e.target.value)}
                    className="h-11 bg-input-background border-0"
                  />
                </div>
              </div>
              <div className="flex items-center gap-2 pt-2">
                <Checkbox
                  id="save-client"
                  checked={saveNewClient}
                  onCheckedChange={(checked) => setSaveNewClient(checked as boolean)}
                />
                <Label htmlFor="save-client" className="cursor-pointer">
                  Save this client to my database for future use
                </Label>
              </div>
            </div>
          )}
        </Card>

        {/* Flight Details */}
        <Card className="p-6">
          <div className="flex items-center gap-2 mb-6">
            <Plane className="h-5 w-5 text-[#335cff]" />
            <h2>Flight Details</h2>
          </div>

          <div className="space-y-6">
            {/* Trip Type Selection */}
            <div className="space-y-2">
              <Label>Trip Type</Label>
              <div className="inline-flex gap-1 p-1 bg-muted rounded-lg">
                <button
                  type="button"
                  onClick={() => setTripType('one-way')}
                  className={`px-4 py-2 rounded-md transition-colors ${
                    tripType === 'one-way'
                      ? 'bg-background shadow-sm'
                      : 'hover:bg-background/50'
                  }`}
                >
                  One Way
                </button>
                <button
                  type="button"
                  onClick={() => setTripType('round-trip')}
                  className={`px-4 py-2 rounded-md transition-colors ${
                    tripType === 'round-trip'
                      ? 'bg-background shadow-sm'
                      : 'hover:bg-background/50'
                  }`}
                >
                  Round Trip
                </button>
                <button
                  type="button"
                  onClick={() => setTripType('multi-leg')}
                  className={`px-4 py-2 rounded-md transition-colors ${
                    tripType === 'multi-leg'
                      ? 'bg-background shadow-sm'
                      : 'hover:bg-background/50'
                  }`}
                >
                  Multi Leg
                </button>
              </div>
            </div>

            {/* One-Way and Round-Trip Forms */}
            {(tripType === 'one-way' || tripType === 'round-trip') && (
              <div className="space-y-4">
                <div className="grid md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="departure">Departure</Label>
                    <div className="relative">
                      <MapPin className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
                      <Input
                        id="departure"
                        placeholder="TEB - Teterboro (optional)"
                        value={departure}
                        onChange={(e) => setDeparture(e.target.value)}
                        className="h-11 bg-input-background border-0 pl-10"
                      />
                    </div>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="arrival">Arrival</Label>
                    <div className="relative">
                      <MapPin className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
                      <Input
                        id="arrival"
                        placeholder="MIA - Miami (optional)"
                        value={arrival}
                        onChange={(e) => setArrival(e.target.value)}
                        className="h-11 bg-input-background border-0 pl-10"
                      />
                    </div>
                  </div>
                </div>
                <div className="grid md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="departure-date">Departure Date</Label>
                    <div className="relative">
                      <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
                      <Input
                        id="departure-date"
                        type="date"
                        value={departureDate}
                        onChange={(e) => setDepartureDate(e.target.value)}
                        className="h-11 bg-input-background border-0 pl-10"
                      />
                    </div>
                  </div>
                  {tripType === 'round-trip' && (
                    <div className="space-y-2">
                      <Label htmlFor="return-date">Return Date</Label>
                      <div className="relative">
                        <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
                        <Input
                          id="return-date"
                          type="date"
                          value={returnDate}
                          onChange={(e) => setReturnDate(e.target.value)}
                          className="h-11 bg-input-background border-0 pl-10"
                        />
                      </div>
                    </div>
                  )}
                </div>
                <div className="grid md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="passengers">Passengers</Label>
                    <div className="relative">
                      <Users className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
                      <Input
                        id="passengers"
                        type="number"
                        min="1"
                        placeholder="6 (default)"
                        value={passengers}
                        onChange={(e) => setPassengers(e.target.value)}
                        className="h-11 bg-input-background border-0 pl-10"
                      />
                    </div>
                  </div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="notes">Notes (Optional)</Label>
                  <Textarea
                    id="notes"
                    placeholder="Special requirements or preferences..."
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    className="min-h-[100px] bg-input-background border-0 resize-none"
                  />
                </div>
              </div>
            )}

            {/* Multi-Leg Form */}
            {tripType === 'multi-leg' && (
              <div className="space-y-4">
                {legs.map((leg, index) => (
                  <div key={index} className="p-4 border border-border rounded-lg space-y-4">
                    <div className="flex items-center justify-between mb-2">
                      <h3 className="font-semibold">Leg {index + 1}</h3>
                      {legs.length > 1 && (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => handleRemoveLeg(index)}
                          className="h-8 w-8 p-0"
                        >
                          <X className="h-4 w-4" />
                        </Button>
                      )}
                    </div>

                    <div className="grid md:grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label htmlFor={`leg-${index}-departure`}>
                          Departure
                        </Label>
                        <div className="relative">
                          <MapPin className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
                          <Input
                            id={`leg-${index}-departure`}
                            placeholder="TEB - Teterboro (optional)"
                            value={leg.departure}
                            onChange={(e) => handleUpdateLeg(index, 'departure', e.target.value)}
                            className="h-11 bg-input-background border-0 pl-10"
                          />
                        </div>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor={`leg-${index}-arrival`}>
                          Arrival
                        </Label>
                        <div className="relative">
                          <MapPin className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
                          <Input
                            id={`leg-${index}-arrival`}
                            placeholder="MIA - Miami (optional)"
                            value={leg.arrival}
                            onChange={(e) => handleUpdateLeg(index, 'arrival', e.target.value)}
                            className="h-11 bg-input-background border-0 pl-10"
                          />
                        </div>
                      </div>
                    </div>

                    <div className="grid md:grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label htmlFor={`leg-${index}-date`}>
                          Date
                        </Label>
                        <div className="relative">
                          <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
                          <Input
                            id={`leg-${index}-date`}
                            type="date"
                            value={leg.date}
                            onChange={(e) => handleUpdateLeg(index, 'date', e.target.value)}
                            className="h-11 bg-input-background border-0 pl-10"
                          />
                        </div>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor={`leg-${index}-passengers`}>
                          Passengers
                        </Label>
                        <div className="relative">
                          <Users className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
                          <Input
                            id={`leg-${index}-passengers`}
                            type="number"
                            min="1"
                            placeholder="6 (default)"
                            value={leg.passengers || ''}
                            onChange={(e) => handleUpdateLeg(index, 'passengers', parseInt(e.target.value) || 0)}
                            className="h-11 bg-input-background border-0 pl-10"
                          />
                        </div>
                      </div>
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor={`leg-${index}-notes`}>Notes (Optional)</Label>
                      <Textarea
                        id={`leg-${index}-notes`}
                        placeholder="Special requirements for this leg..."
                        value={leg.notes || ''}
                        onChange={(e) => handleUpdateLeg(index, 'notes', e.target.value)}
                        className="min-h-[80px] bg-input-background border-0 resize-none"
                      />
                    </div>
                  </div>
                ))}

                <Button
                  type="button"
                  variant="outline"
                  onClick={handleAddLeg}
                  className="w-full gap-2"
                >
                  <Plus className="h-4 w-4" />
                  Add Another Leg
                </Button>
              </div>
            )}
          </div>
        </Card>

        {/* Aircraft Options with Pricing */}
        <Card className="p-6">
          <div className="flex items-center gap-2 mb-6">
            <DollarSign className="h-5 w-5 text-[#335cff]" />
            <h2>Aircraft Options & Pricing</h2>
            <Badge variant="secondary" className="ml-auto">
              {shortlistedAircraft.length} option{shortlistedAircraft.length !== 1 ? 's' : ''}
            </Badge>
          </div>

          <div className="space-y-4">
            {shortlistedAircraft.map((aircraft) => (
              <div key={aircraft.id} className="p-4 border border-border rounded-lg">
                <div className="flex items-start gap-4">
                  <div className="flex-shrink-0">
                    <TrustScoreGauge score={aircraft.operator.trustScore} size="sm" />
                  </div>
                  
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-2 mb-3">
                      <div>
                        <button
                          type="button"
                          onClick={() => onViewAircraftDetails(aircraft)}
                          className="hover:underline text-left"
                        >
                          <h4 className="font-semibold">
                            {aircraft.manufacturer} {aircraft.model}
                          </h4>
                          <p className="text-sm text-muted-foreground">
                            {aircraft.tailNumber} • {aircraft.operator.name}
                          </p>
                        </button>
                      </div>
                      <div className="flex gap-2">
                        {aircraft.operator.certifications.slice(0, 2).map((cert, i) => (
                          <Badge key={i} variant="secondary" className="text-xs">
                            {cert}
                          </Badge>
                        ))}
                      </div>
                    </div>

                    <div className="grid md:grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label htmlFor={`operator-price-${aircraft.id}`}>
                          Operator Price ($)
                        </Label>
                        <Input
                          id={`operator-price-${aircraft.id}`}
                          type="number"
                          min="0"
                          step="100"
                          value={aircraftPricing[aircraft.id]?.operatorPrice || ''}
                          onChange={(e) => handleUpdateAircraftPricing(
                            aircraft.id,
                            'operatorPrice',
                            parseFloat(e.target.value) || 0
                          )}
                          className="h-11 bg-input-background border-0"
                          placeholder="Enter operator's quoted price"
                        />
                        <p className="text-xs text-muted-foreground">
                          Base rate: ${aircraft.hourlyRate.toLocaleString()}/hr
                        </p>
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor={`my-price-${aircraft.id}`}>
                          My Price ($)
                        </Label>
                        <Input
                          id={`my-price-${aircraft.id}`}
                          type="number"
                          min="0"
                          step="100"
                          value={aircraftPricing[aircraft.id]?.myPrice || ''}
                          onChange={(e) => handleUpdateAircraftPricing(
                            aircraft.id,
                            'myPrice',
                            parseFloat(e.target.value) || 0
                          )}
                          className="h-11 bg-input-background border-0"
                          placeholder="Enter your client price"
                        />
                        {aircraftPricing[aircraft.id]?.operatorPrice > 0 && aircraftPricing[aircraft.id]?.myPrice > 0 && (
                          <p className="text-xs text-muted-foreground">
                            Margin: ${(aircraftPricing[aircraft.id].myPrice - aircraftPricing[aircraft.id].operatorPrice).toLocaleString()} 
                            ({(((aircraftPricing[aircraft.id].myPrice - aircraftPricing[aircraft.id].operatorPrice) / aircraftPricing[aircraft.id].operatorPrice) * 100).toFixed(1)}%)
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* Quote Settings */}
        <Card className="p-6">
          <div className="flex items-center gap-2 mb-6">
            <FileText className="h-5 w-5 text-[#335cff]" />
            <h2>Quote Settings</h2>
          </div>

          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="quote-title">Quote Title</Label>
              <Input
                id="quote-title"
                placeholder="e.g., Miami Trip - October 2025 (optional)"
                value={quoteTitle}
                onChange={(e) => setQuoteTitle(e.target.value)}
                className="h-11 bg-input-background border-0"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="quote-message">Message to Client (Optional)</Label>
              <Textarea
                id="quote-message"
                placeholder="Add a personalized message to your client..."
                value={quoteMessage}
                onChange={(e) => setQuoteMessage(e.target.value)}
                className="min-h-[100px] bg-input-background border-0 resize-none"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="expires-at">Expiration Date</Label>
              <div className="relative">
                <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
                <Input
                  id="expires-at"
                  type="date"
                  value={expiresAt}
                  onChange={(e) => setExpiresAt(e.target.value)}
                  className="h-11 bg-input-background border-0 pl-10"
                />
              </div>
              <p className="text-xs text-muted-foreground">
                Quote will expire on this date
              </p>
            </div>
          </div>
        </Card>

        {/* Action Buttons */}
        <div className="flex items-center justify-between pt-4">
          <Button
            type="button"
            variant="outline"
            onClick={onCancel}
          >
            Cancel
          </Button>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => handleSubmit('draft')}
              disabled={!isFormValid()}
              className="gap-2"
            >
              <Save className="h-4 w-4" />
              Save as Draft
            </Button>
            <Button
              type="button"
              onClick={() => handleSubmit('preview')}
              disabled={!isFormValid()}
              className="bg-[#335cff] hover:bg-[#2847cc] gap-2"
            >
              <Send className="h-4 w-4" />
              Preview & Send
            </Button>
          </div>
        </div>
      </div>

      {/* Save Client Confirmation Dialog */}
      <Dialog open={showSaveClientDialog} onOpenChange={setShowSaveClientDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Save Client to Database?</DialogTitle>
            <DialogDescription>
              Do you want to save "{newClientName}" to your client database for future use?
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Name:</span>
                <span>{newClientName}</span>
              </div>
              {newClientCompany && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Company:</span>
                  <span>{newClientCompany}</span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-muted-foreground">Email:</span>
                <span>{newClientEmail}</span>
              </div>
              {newClientPhone && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Phone:</span>
                  <span>{newClientPhone}</span>
                </div>
              )}
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setShowSaveClientDialog(false);
                setSaveNewClient(false);
                handleSubmit('preview');
              }}
            >
              Skip & Preview Quote
            </Button>
            <Button
              onClick={() => handleSaveClientAndSubmit('preview')}
              className="bg-[#335cff] hover:bg-[#2847cc]"
            >
              <Save className="h-4 w-4 mr-2" />
              Save & Preview Quote
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
