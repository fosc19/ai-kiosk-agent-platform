<script lang="ts">
  import { onMount } from 'svelte';
  import * as d3 from 'd3';
  import type { WaterfallBar } from './types';

  export let bars: WaterfallBar[] = [];
  export let title: string = 'Waterfall Chart';
  export let width: number = 1000;
  export let height: number = 400;

  let svg: SVGSVGElement;
  let tooltip: HTMLDivElement;

  const margin = { top: 40, right: 20, bottom: 60, left: 200 };
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;

  function renderChart() {
    if (!svg || bars.length === 0) return;

    // Clear previous content
    d3.select(svg).selectAll('*').remove();

    // Calculate max duration
    const maxTime = Math.max(...bars.map(b => b.start_ms + b.duration_ms));

    // Create scales
    const xScale = d3.scaleLinear()
      .domain([0, maxTime])
      .range([0, innerWidth]);

    const yScale = d3.scaleBand()
      .domain(bars.map((_, i) => i.toString()))
      .range([0, innerHeight])
      .padding(0.2);

    // Create SVG group
    const g = d3.select(svg)
      .append('g')
      .attr('transform', `translate(${margin.left},${margin.top})`);

    // Add title
    d3.select(svg)
      .append('text')
      .attr('x', width / 2)
      .attr('y', 20)
      .attr('text-anchor', 'middle')
      .attr('font-size', '16px')
      .attr('font-weight', 'bold')
      .attr('fill', '#1f2937')
      .text(title);

    // Add X axis
    const xAxis = d3.axisBottom(xScale)
      .ticks(10)
      .tickFormat(d => `${d}ms`);

    g.append('g')
      .attr('transform', `translate(0,${innerHeight})`)
      .call(xAxis)
      .selectAll('text')
      .attr('fill', '#6b7280');

    // X axis label
    g.append('text')
      .attr('x', innerWidth / 2)
      .attr('y', innerHeight + 45)
      .attr('text-anchor', 'middle')
      .attr('font-size', '12px')
      .attr('fill', '#6b7280')
      .text('Time (ms)');

    // Add bars
    const barGroups = g.selectAll('.bar-group')
      .data(bars)
      .enter()
      .append('g')
      .attr('class', 'bar-group');

    // Bar rectangles
    barGroups.append('rect')
      .attr('x', d => xScale(d.start_ms))
      .attr('y', (_, i) => yScale(i.toString()) || 0)
      .attr('width', d => xScale(d.duration_ms))
      .attr('height', yScale.bandwidth())
      .attr('fill', d => d.color)
      .attr('opacity', 0.8)
      .attr('rx', 3)
      .on('mouseover', function(event, d) {
        d3.select(this).attr('opacity', 1);
        showTooltip(event, d);
      })
      .on('mouseout', function() {
        d3.select(this).attr('opacity', 0.8);
        hideTooltip();
      });

    // Duration text on bars (if wide enough)
    barGroups.append('text')
      .attr('x', d => xScale(d.start_ms) + xScale(d.duration_ms) / 2)
      .attr('y', (_, i) => (yScale(i.toString()) || 0) + yScale.bandwidth() / 2)
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'middle')
      .attr('font-size', '11px')
      .attr('fill', 'white')
      .attr('pointer-events', 'none')
      .text(d => xScale(d.duration_ms) > 40 ? `${d.duration_ms.toFixed(0)}ms` : '');

    // Labels on the left
    barGroups.append('text')
      .attr('x', -10)
      .attr('y', (_, i) => (yScale(i.toString()) || 0) + yScale.bandwidth() / 2)
      .attr('text-anchor', 'end')
      .attr('dominant-baseline', 'middle')
      .attr('font-size', '12px')
      .attr('fill', d => d.violation ? '#ef4444' : '#374151')
      .text(d => d.label + (d.violation ? ' 🔴' : ''));

    // Grid lines
    g.selectAll('.grid-line')
      .data(xScale.ticks(10))
      .enter()
      .append('line')
      .attr('class', 'grid-line')
      .attr('x1', d => xScale(d))
      .attr('x2', d => xScale(d))
      .attr('y1', 0)
      .attr('y2', innerHeight)
      .attr('stroke', '#e5e7eb')
      .attr('stroke-width', 1)
      .attr('stroke-dasharray', '2,2');
  }

  function showTooltip(event: MouseEvent, bar: WaterfallBar) {
    if (!tooltip) return;

    tooltip.style.display = 'block';
    tooltip.style.left = `${event.pageX + 10}px`;
    tooltip.style.top = `${event.pageY + 10}px`;
    tooltip.innerHTML = `<pre>${bar.details}</pre>`;
  }

  function hideTooltip() {
    if (!tooltip) return;
    tooltip.style.display = 'none';
  }

  onMount(() => {
    renderChart();
  });

  $: if (svg && bars.length > 0) {
    renderChart();
  }
</script>

<div class="waterfall-container">
  <svg bind:this={svg} {width} {height}></svg>
  <div bind:this={tooltip} class="tooltip"></div>
</div>

<style>
  .waterfall-container {
    position: relative;
    width: 100%;
    overflow-x: auto;
  }

  svg {
    display: block;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  }

  .tooltip {
    position: fixed;
    display: none;
    background: rgba(0, 0, 0, 0.9);
    color: white;
    padding: 10px;
    border-radius: 6px;
    font-size: 12px;
    font-family: 'Courier New', monospace;
    pointer-events: none;
    z-index: 1000;
    max-width: 400px;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
    white-space: pre-wrap;
    word-wrap: break-word;
  }
</style>
