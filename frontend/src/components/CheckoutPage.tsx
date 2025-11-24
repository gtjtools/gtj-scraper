import { useState } from 'react';
import { Card } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Separator } from './ui/separator';
import { Badge } from './ui/badge';
import { Checkbox } from './ui/checkbox';
import { 
  ArrowLeft, 
  CreditCard,
  Lock,
  Users,
  MapPin,
  Calendar,
  Plane,
  CheckCircle2
} from 'lucide-react';
import { Aircraft } from '../lib/mock-data';
import { ImageWithFallback } from './figma/ImageWithFallback';

interface CheckoutPageProps {
  aircraft: Aircraft;
  pricing: {
    operatorPrice: number;
    myPrice: number;
  };
  tripDetails: {
    departure: string;
    arrival: string;
    date: string;
    passengers: number;
    clientName: string;
  };
  onBack: () => void;
  onComplete: () => void;
}

export function CheckoutPage({ aircraft, pricing, tripDetails, onBack, onComplete }: CheckoutPageProps) {
  const [agreed, setAgreed] = useState(false);
  const [paymentProcessing, setPaymentProcessing] = useState(false);

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

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setPaymentProcessing(true);
    
    // Simulate payment processing
    setTimeout(() => {
      setPaymentProcessing(false);
      onComplete();
    }, 2000);
  };

  const depositAmount = pricing.myPrice * 0.3; // 30% deposit
  const taxAmount = pricing.myPrice * 0.075; // 7.5% tax
  const totalAmount = pricing.myPrice + taxAmount;

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Button
          variant="outline"
          onClick={onBack}
          className="gap-2"
        >
          <ArrowLeft className="h-4 w-4" />
          Back
        </Button>
        <div>
          <h1 className="text-3xl font-bold">Secure Checkout</h1>
          <p className="text-muted-foreground mt-1">
            Complete your booking for {tripDetails.clientName}
          </p>
        </div>
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* Main Content - Payment Form */}
        <div className="lg:col-span-2 space-y-6">
          {/* Security Notice */}
          <Card className="p-4 bg-[#335cff]/5 border-[#335cff]/20">
            <div className="flex items-center gap-3">
              <Lock className="h-5 w-5 text-[#335cff]" />
              <div>
                <p className="font-semibold text-sm">Secure Payment</p>
                <p className="text-xs text-muted-foreground">
                  Your payment information is encrypted and secure
                </p>
              </div>
            </div>
          </Card>

          {/* Payment Information */}
          <Card className="p-6">
            <h2 className="text-xl font-bold mb-4">Payment Information</h2>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <Label htmlFor="cardName">Cardholder Name</Label>
                <Input
                  id="cardName"
                  placeholder="John Doe"
                  required
                />
              </div>

              <div>
                <Label htmlFor="cardNumber">Card Number</Label>
                <div className="relative">
                  <Input
                    id="cardNumber"
                    placeholder="1234 5678 9012 3456"
                    maxLength={19}
                    required
                  />
                  <CreditCard className="absolute right-3 top-1/2 -translate-y-1/2 h-5 w-5 text-muted-foreground" />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="expiry">Expiration Date</Label>
                  <Input
                    id="expiry"
                    placeholder="MM/YY"
                    maxLength={5}
                    required
                  />
                </div>
                <div>
                  <Label htmlFor="cvv">CVV</Label>
                  <Input
                    id="cvv"
                    placeholder="123"
                    maxLength={4}
                    type="password"
                    required
                  />
                </div>
              </div>

              <Separator className="my-6" />

              {/* Billing Information */}
              <h3 className="font-semibold mb-4">Billing Address</h3>
              
              <div>
                <Label htmlFor="address">Street Address</Label>
                <Input
                  id="address"
                  placeholder="123 Main St"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="city">City</Label>
                  <Input
                    id="city"
                    placeholder="New York"
                    required
                  />
                </div>
                <div>
                  <Label htmlFor="state">State</Label>
                  <Input
                    id="state"
                    placeholder="NY"
                    required
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="zip">ZIP Code</Label>
                  <Input
                    id="zip"
                    placeholder="10001"
                    required
                  />
                </div>
                <div>
                  <Label htmlFor="country">Country</Label>
                  <Input
                    id="country"
                    placeholder="United States"
                    required
                  />
                </div>
              </div>

              <Separator className="my-6" />

              {/* Terms and Conditions */}
              <div className="flex items-start gap-3">
                <Checkbox
                  id="terms"
                  checked={agreed}
                  onCheckedChange={(checked) => setAgreed(checked as boolean)}
                />
                <div className="flex-1">
                  <label
                    htmlFor="terms"
                    className="text-sm cursor-pointer"
                  >
                    I agree to the{' '}
                    <a href="#" className="text-[#335cff] hover:underline">
                      Terms and Conditions
                    </a>
                    {' '}and{' '}
                    <a href="#" className="text-[#335cff] hover:underline">
                      Cancellation Policy
                    </a>
                  </label>
                </div>
              </div>

              {/* Submit Button */}
              <Button
                type="submit"
                disabled={!agreed || paymentProcessing}
                className="w-full bg-[#335cff] hover:bg-[#2847cc] gap-2 h-12"
              >
                {paymentProcessing ? (
                  <>Processing...</>
                ) : (
                  <>
                    <Lock className="h-4 w-4" />
                    Complete Booking - {formatCurrency(depositAmount)} Deposit
                  </>
                )}
              </Button>

              <p className="text-xs text-center text-muted-foreground">
                You will be charged a deposit of {formatCurrency(depositAmount)}. 
                The remaining balance of {formatCurrency(totalAmount - depositAmount)} is due before departure.
              </p>
            </form>
          </Card>
        </div>

        {/* Sidebar - Order Summary */}
        <div className="space-y-6">
          {/* Trip Summary */}
          <Card className="p-6 sticky top-6">
            <h2 className="font-bold mb-4">Booking Summary</h2>
            
            {/* Aircraft Preview */}
            <div className="mb-4">
              <div className="relative aspect-video rounded-lg overflow-hidden bg-slate-100 mb-3">
                <ImageWithFallback
                  src={aircraft.imageUrl}
                  alt={`${aircraft.manufacturer} ${aircraft.model}`}
                  className="w-full h-full object-cover"
                />
              </div>
              <h3 className="font-semibold">
                {aircraft.manufacturer} {aircraft.model}
              </h3>
              <p className="text-sm text-muted-foreground">
                Tail: {aircraft.tailNumber}
              </p>
            </div>

            <Separator className="my-4" />

            {/* Trip Details */}
            <div className="space-y-3 text-sm">
              <div className="flex items-start gap-2">
                <MapPin className="h-4 w-4 text-muted-foreground mt-0.5 flex-shrink-0" />
                <div className="flex-1">
                  <p className="text-muted-foreground">Route</p>
                  <p className="font-semibold">
                    {tripDetails.departure} → {tripDetails.arrival}
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-2">
                <Calendar className="h-4 w-4 text-muted-foreground mt-0.5 flex-shrink-0" />
                <div className="flex-1">
                  <p className="text-muted-foreground">Date</p>
                  <p className="font-semibold">{formatDate(tripDetails.date)}</p>
                </div>
              </div>

              <div className="flex items-start gap-2">
                <Users className="h-4 w-4 text-muted-foreground mt-0.5 flex-shrink-0" />
                <div className="flex-1">
                  <p className="text-muted-foreground">Passengers</p>
                  <p className="font-semibold">{tripDetails.passengers} passengers</p>
                </div>
              </div>

              <div className="flex items-start gap-2">
                <Plane className="h-4 w-4 text-muted-foreground mt-0.5 flex-shrink-0" />
                <div className="flex-1">
                  <p className="text-muted-foreground">Operator</p>
                  <p className="font-semibold">{aircraft.operator.name}</p>
                </div>
              </div>
            </div>

            <Separator className="my-4" />

            {/* Price Breakdown */}
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Base Price</span>
                <span className="font-semibold">{formatCurrency(pricing.myPrice)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Taxes & Fees</span>
                <span className="font-semibold">{formatCurrency(taxAmount)}</span>
              </div>
              <Separator className="my-2" />
              <div className="flex justify-between text-base">
                <span className="font-bold">Total</span>
                <span className="font-bold">{formatCurrency(totalAmount)}</span>
              </div>
              <div className="flex justify-between pt-2 border-t">
                <span className="text-muted-foreground">Due Today (30%)</span>
                <span className="font-bold text-[#335cff]">{formatCurrency(depositAmount)}</span>
              </div>
            </div>

            <div className="mt-4 p-3 bg-green-50 border border-green-200 rounded-lg">
              <div className="flex items-start gap-2">
                <CheckCircle2 className="h-4 w-4 text-green-600 mt-0.5 flex-shrink-0" />
                <p className="text-xs text-green-800">
                  Free cancellation up to 7 days before departure
                </p>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
