import { themeColor, useChartInk } from '../../lib/themeColor';
import React from 'react';
import { useTheme } from '../../context/ThemeContext';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';

interface CompetencyBarChartProps {
  data: Array<{
    name: string;
    LU: number;
    CU: number;
    AU: number;
    CT: number;
  }>;
  height?: number;
}

export const CompetencyBarChart: React.FC<CompetencyBarChartProps> = ({
  data,
  height = 280,
}) => {
  const { uiMode } = useTheme();
  const analytics = uiMode === 'analytics';
  const series = analytics
    ? ['#1E3A8A', '#2563EB', '#0E7490', '#7C3AED']
    : ['#3B82F6', '#10B981', '#F59E0B', '#8B5CF6'];
  const ink = useChartInk();
  const grid = ink.grid;
  const tick = ink.muted;
  return (
    <div style={{ width: '100%', height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data}
          margin={{ top: 15, right: 15, left: -15, bottom: 5 }}
          barGap={3}
          barSize={14}
        >
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={grid} />
          <XAxis
            dataKey="name"
            tick={{ fill: tick, fontSize: 11 }}
            axisLine={{ stroke: grid }}
            tickLine={false}
          />
          <YAxis
            domain={[0, 100]}
            tick={{ fill: tick, fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: themeColor('--surface-card', '#FFFFFF'),
              color: ink.text,
              borderRadius: '8px',
              border: `1px solid ${grid}`,
              boxShadow: analytics ? 'none' : '0 4px 6px -1px rgba(0,0,0,0.1)',
              fontSize: '12px',
            }}
          />
          <Legend
            verticalAlign="top"
            align="right"
            wrapperStyle={{ paddingBottom: '12px', fontSize: '11px' }}
          />
          <Bar dataKey="LU" name="LU (Language)" fill={series[0]} radius={[3, 3, 0, 0]} />
          <Bar dataKey="CU" name="CU (Concept)" fill={series[1]} radius={[3, 3, 0, 0]} />
          <Bar dataKey="AU" name="AU (Application)" fill={series[2]} radius={[3, 3, 0, 0]} />
          <Bar dataKey="CT" name="CT (Critical Thinking)" fill={series[3]} radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
};

