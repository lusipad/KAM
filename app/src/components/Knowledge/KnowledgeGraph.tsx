import { useEffect, useRef, useState } from 'react';
import { ZoomIn, ZoomOut, Maximize, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAppStore } from '@/store/appStore';
import type { GraphData, GraphNode, GraphEdge } from '@/types';

interface KnowledgeGraphProps {
  onSelectNode?: (nodeId: string) => void;
  highlightNodeId?: string;
}

export function KnowledgeGraph({ onSelectNode, highlightNodeId }: KnowledgeGraphProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [scale, setScale] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  
  const notes = useAppStore((state) => state.knowledge.notes);
  const links = useAppStore((state) => state.knowledge.links);

  // 构建图谱数据
  const buildGraphData = (): GraphData => {
    const nodes: GraphNode[] = notes.map((note) => ({
      id: note.id,
      title: note.title || '未命名',
      type: 'note',
      metadata: {
        createdAt: note.createdAt,
        updatedAt: note.updatedAt,
        wordCount: note.stats.wordCount,
        tags: note.metadata.tags,
      },
      visual: {
        size: Math.max(20, Math.min(60, 20 + note.stats.backlinkCount * 5)),
        color: note.metadata.tags.length > 0 
          ? `hsl(${note.metadata.tags[0].charCodeAt(0) * 30 % 360}, 70%, 60%)`
          : '#94a3b8',
      },
    }));

    const edges: GraphEdge[] = links
      .filter(link => link.isResolved)
      .map(link => ({
        source: link.sourceNoteId,
        target: link.targetNoteId,
        type: link.type,
        strength: link.isEmbed ? 0.8 : 0.5,
      }));

    return { nodes, edges };
  };

  const graphData = buildGraphData();

  // 简单的力导向布局
  const calculateLayout = () => {
    const width = canvasRef.current?.width || 800;
    const height = canvasRef.current?.height || 600;
    const centerX = width / 2;
    const centerY = height / 2;

    // 初始化位置
    const positions: Record<string, { x: number; y: number; vx: number; vy: number }> = {};
    
    graphData.nodes.forEach((node, i) => {
      const angle = (i / graphData.nodes.length) * Math.PI * 2;
      const radius = Math.min(width, height) * 0.3;
      positions[node.id] = {
        x: centerX + Math.cos(angle) * radius,
        y: centerY + Math.sin(angle) * radius,
        vx: 0,
        vy: 0,
      };
    });

    // 简单的力导向迭代
    for (let iteration = 0; iteration < 50; iteration++) {
      // 斥力
      graphData.nodes.forEach((node1, i) => {
        graphData.nodes.forEach((node2, j) => {
          if (i >= j) return;
          const pos1 = positions[node1.id];
          const pos2 = positions[node2.id];
          const dx = pos1.x - pos2.x;
          const dy = pos1.y - pos2.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const force = 1000 / (dist * dist);
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          
          pos1.vx += fx;
          pos1.vy += fy;
          pos2.vx -= fx;
          pos2.vy -= fy;
        });
      });

      // 引力（边）
      graphData.edges.forEach(edge => {
        const pos1 = positions[edge.source];
        const pos2 = positions[edge.target];
        if (!pos1 || !pos2) return;
        
        const dx = pos2.x - pos1.x;
        const dy = pos2.y - pos1.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const force = (dist - 100) * 0.01 * edge.strength;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        
        pos1.vx += fx;
        pos1.vy += fy;
        pos2.vx -= fx;
        pos2.vy -= fy;
      });

      // 中心引力
      graphData.nodes.forEach(node => {
        const pos = positions[node.id];
        const dx = centerX - pos.x;
        const dy = centerY - pos.y;
        pos.vx += dx * 0.001;
        pos.vy += dy * 0.001;
      });

      // 更新位置
      graphData.nodes.forEach(node => {
        const pos = positions[node.id];
        pos.vx *= 0.8; // 阻尼
        pos.vy *= 0.8;
        pos.x += pos.vx;
        pos.y += pos.vy;
      });
    }

    return positions;
  };

  // 渲染图谱
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const positions = calculateLayout();

    const render = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      
      ctx.save();
      ctx.translate(offset.x, offset.y);
      ctx.scale(scale, scale);

      // 绘制边
      graphData.edges.forEach(edge => {
        const pos1 = positions[edge.source];
        const pos2 = positions[edge.target];
        if (!pos1 || !pos2) return;

        ctx.beginPath();
        ctx.moveTo(pos1.x, pos1.y);
        ctx.lineTo(pos2.x, pos2.y);
        ctx.strokeStyle = edge.strength > 0.7 ? 'rgba(59, 130, 246, 0.4)' : 'rgba(148, 163, 184, 0.2)';
        ctx.lineWidth = edge.strength * 2;
        ctx.stroke();
      });

      // 绘制节点
      graphData.nodes.forEach(node => {
        const pos = positions[node.id];
        const isHovered = hoveredNode === node.id;
        const isHighlighted = highlightNodeId === node.id;
        
        // 节点圆圈
        ctx.beginPath();
        ctx.arc(pos.x, pos.y, node.visual.size / 2, 0, Math.PI * 2);
        ctx.fillStyle = node.visual.color;
        ctx.fill();
        
        // 高亮边框
        if (isHovered || isHighlighted) {
          ctx.strokeStyle = isHighlighted ? '#f59e0b' : '#3b82f6';
          ctx.lineWidth = 3;
          ctx.stroke();
        }
        
        // 节点标签
        ctx.fillStyle = '#1e293b';
        ctx.font = `${isHovered ? 'bold' : 'normal'} 12px sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        
        // 文字背景
        const textWidth = ctx.measureText(node.title).width;
        ctx.fillStyle = 'rgba(255, 255, 255, 0.9)';
        ctx.fillRect(
          pos.x - textWidth / 2 - 4,
          pos.y + node.visual.size / 2 + 2,
          textWidth + 8,
          18
        );
        
        ctx.fillStyle = '#1e293b';
        ctx.fillText(
          node.title.length > 15 ? node.title.slice(0, 15) + '...' : node.title,
          pos.x,
          pos.y + node.visual.size / 2 + 11
        );
      });

      ctx.restore();
    };

    render();
  }, [graphData, scale, offset, hoveredNode, highlightNodeId]);

  // 鼠标事件处理
  const handleMouseDown = (e: React.MouseEvent) => {
    setIsDragging(true);
    setDragStart({ x: e.clientX - offset.x, y: e.clientY - offset.y });
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) return;

    const mouseX = (e.clientX - rect.left - offset.x) / scale;
    const mouseY = (e.clientY - rect.top - offset.y) / scale;

    if (isDragging) {
      setOffset({
        x: e.clientX - dragStart.x,
        y: e.clientY - dragStart.y,
      });
    } else {
      // 检测悬停节点
      const positions = calculateLayout();
      let foundNode: string | null = null;
      
      graphData.nodes.forEach(node => {
        const pos = positions[node.id];
        const dist = Math.sqrt(
          Math.pow(mouseX - pos.x, 2) + Math.pow(mouseY - pos.y, 2)
        );
        if (dist < node.visual.size / 2) {
          foundNode = node.id;
        }
      });
      
      setHoveredNode(foundNode);
    }
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  const handleClick = () => {
    if (hoveredNode && onSelectNode) {
      onSelectNode(hoveredNode);
    }
  };

  const handleZoomIn = () => setScale(s => Math.min(s * 1.2, 3));
  const handleZoomOut = () => setScale(s => Math.max(s / 1.2, 0.3));
  const handleReset = () => {
    setScale(1);
    setOffset({ x: 0, y: 0 });
  };

  return (
    <div className="flex flex-col h-full">
      {/* 工具栏 */}
      <div className="flex items-center justify-between p-2 border-b bg-card/50">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">知识图谱</span>
          <span className="text-xs text-muted-foreground">
            {graphData.nodes.length} 节点 · {graphData.edges.length} 连接
          </span>
        </div>
        <div className="flex items-center gap-1">
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={handleZoomIn}>
            <ZoomIn className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={handleZoomOut}>
            <ZoomOut className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={handleReset}>
            <Maximize className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8">
            <RefreshCw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* 画布 */}
      <div className="flex-1 relative overflow-hidden bg-slate-50 dark:bg-slate-900">
        <canvas
          ref={canvasRef}
          width={1200}
          height={800}
          className="absolute inset-0 cursor-grab active:cursor-grabbing"
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseUp}
          onClick={handleClick}
        />
        
        {/* 缩放指示器 */}
        <div className="absolute bottom-4 right-4 bg-background/80 backdrop-blur px-2 py-1 rounded text-xs">
          {Math.round(scale * 100)}%
        </div>
      </div>
    </div>
  );
}
