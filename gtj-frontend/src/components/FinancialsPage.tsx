import { BrokerPerformance } from '../lib/mock-data';
import { Card } from './ui/card';
import { TrendingUp, DollarSign, Target, Award, Users, Building2 } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line } from 'recharts';

interface FinancialsPageProps {
  performance: BrokerPerformance;
}

export function FinancialsPage({ performance }: FinancialsPageProps) {
  const stats = [
    {
      title: 'Total Revenue',
      value: `$${(performance.totalRevenue / 1000).toFixed(0)}k`,
      change: '+12.5%',
      icon: DollarSign,
      color: 'text-green-600',
      bgColor: 'bg-green-50'
    },
    {
      title: 'Total Commissions',
      value: `$${(performance.totalCommissions / 1000).toFixed(1)}k`,
      change: '+8.3%',
      icon: TrendingUp,
      color: 'text-blue-600',
      bgColor: 'bg-blue-50'
    },
    {
      title: 'Total Bookings',
      value: performance.totalBookings.toString(),
      change: '+15.2%',
      icon: Target,
      color: 'text-purple-600',
      bgColor: 'bg-purple-50'
    },
    {
      title: 'Conversion Rate',
      value: `${performance.conversionRate}%`,
      change: '+5.1%',
      icon: Award,
      color: 'text-orange-600',
      bgColor: 'bg-orange-50'
    }
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Financials</h1>
        <p className="text-muted-foreground mt-1">
          Track your broker performance and revenue metrics
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => {
          const Icon = stat.icon;
          return (
            <Card key={stat.title} className="p-6">
              <div className="flex items-center justify-between mb-4">
                <div className={`p-3 rounded-lg ${stat.bgColor}`}>
                  <Icon className={`h-5 w-5 ${stat.color}`} />
                </div>
                <span className="text-sm text-green-600">{stat.change}</span>
              </div>
              <div>
                <p className="text-2xl font-bold mb-1">{stat.value}</p>
                <p className="text-sm text-muted-foreground">{stat.title}</p>
              </div>
            </Card>
          );
        })}
      </div>

      {/* Charts */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Revenue Chart */}
        <Card className="p-6">
          <h3 className="font-semibold mb-4">Revenue Trend</h3>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={performance.monthlyData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis 
                dataKey="month" 
                stroke="#6b7280"
                tick={{ fontSize: 12 }}
              />
              <YAxis 
                stroke="#6b7280"
                tick={{ fontSize: 12 }}
                tickFormatter={(value) => `$${value / 1000}k`}
              />
              <Tooltip 
                formatter={(value: number) => `$${value.toLocaleString()}`}
                contentStyle={{ 
                  backgroundColor: 'white', 
                  border: '1px solid #e5e7eb',
                  borderRadius: '8px'
                }}
              />
              <Line 
                type="monotone" 
                dataKey="revenue" 
                stroke="#335cff" 
                strokeWidth={2}
                dot={{ fill: '#335cff', r: 4 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </Card>

        {/* Commissions Chart */}
        <Card className="p-6">
          <h3 className="font-semibold mb-4">Commissions Earned</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={performance.monthlyData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis 
                dataKey="month" 
                stroke="#6b7280"
                tick={{ fontSize: 12 }}
              />
              <YAxis 
                stroke="#6b7280"
                tick={{ fontSize: 12 }}
                tickFormatter={(value) => `$${value / 1000}k`}
              />
              <Tooltip 
                formatter={(value: number) => `$${value.toLocaleString()}`}
                contentStyle={{ 
                  backgroundColor: 'white', 
                  border: '1px solid #e5e7eb',
                  borderRadius: '8px'
                }}
              />
              <Bar 
                dataKey="commissions" 
                fill="#10b981"
                radius={[4, 4, 0, 0]}
              />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      {/* Additional Metrics */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <Card className="p-6">
          <div className="flex items-center gap-3 mb-3">
            <div className="p-2 bg-blue-50 rounded-lg">
              <DollarSign className="h-5 w-5 text-blue-600" />
            </div>
            <h3 className="font-semibold">Average Booking Value</h3>
          </div>
          <p className="text-2xl font-bold">
            ${performance.averageBookingValue.toLocaleString()}
          </p>
          <p className="text-sm text-muted-foreground mt-1">
            Per successful booking
          </p>
        </Card>

        <Card className="p-6">
          <div className="flex items-center gap-3 mb-3">
            <div className="p-2 bg-purple-50 rounded-lg">
              <Users className="h-5 w-5 text-purple-600" />
            </div>
            <h3 className="font-semibold">Top Client</h3>
          </div>
          <p className="text-2xl font-bold">{performance.topClient}</p>
          <p className="text-sm text-muted-foreground mt-1">
            Highest booking volume
          </p>
        </Card>

        <Card className="p-6">
          <div className="flex items-center gap-3 mb-3">
            <div className="p-2 bg-green-50 rounded-lg">
              <Building2 className="h-5 w-5 text-green-600" />
            </div>
            <h3 className="font-semibold">Top Operator</h3>
          </div>
          <p className="text-2xl font-bold">{performance.topOperator}</p>
          <p className="text-sm text-muted-foreground mt-1">
            Most bookings completed
          </p>
        </Card>
      </div>

      {/* Bookings Table */}
      <Card className="p-6">
        <h3 className="font-semibold mb-4">Monthly Bookings</h3>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b">
                <th className="text-left py-3 px-4 text-sm font-medium text-muted-foreground">Month</th>
                <th className="text-right py-3 px-4 text-sm font-medium text-muted-foreground">Bookings</th>
                <th className="text-right py-3 px-4 text-sm font-medium text-muted-foreground">Revenue</th>
                <th className="text-right py-3 px-4 text-sm font-medium text-muted-foreground">Commissions</th>
              </tr>
            </thead>
            <tbody>
              {performance.monthlyData.map((month) => (
                <tr key={month.month} className="border-b last:border-0 hover:bg-muted/50">
                  <td className="py-3 px-4">{month.month}</td>
                  <td className="py-3 px-4 text-right">{month.bookings}</td>
                  <td className="py-3 px-4 text-right">${month.revenue.toLocaleString()}</td>
                  <td className="py-3 px-4 text-right text-green-600 font-medium">
                    ${month.commissions.toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
