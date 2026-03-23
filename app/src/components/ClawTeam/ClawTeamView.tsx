import { useState } from 'react';
import { 
  Bot, Plus, Play, Users, Zap, CheckCircle, 
  XCircle, Clock, MoreVertical, Trash2, Edit
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { 
  Dialog, 
  DialogContent, 
  DialogHeader, 
  DialogTitle, 
  DialogDescription,
  DialogFooter,
  DialogTrigger
} from '@/components/ui/dialog';
import { 
  DropdownMenu, 
  DropdownMenuContent, 
  DropdownMenuItem, 
  DropdownMenuTrigger 
} from '@/components/ui/dropdown-menu';
import { useApiStore } from '@/store/apiStore';
import { useEffect } from 'react';
import { cn } from '@/lib/utils';
import type { Agent, AgentTeam, Task, AgentRole, TeamTopology } from '@/types';

const roleConfig: Record<AgentRole, { label: string; color: string; description: string }> = {
  planner: { label: '规划者', color: 'bg-blue-500', description: '制定执行策略' },
  decomposer: { label: '分解者', color: 'bg-cyan-500', description: '拆分复杂任务' },
  router: { label: '路由者', color: 'bg-indigo-500', description: '选择执行路径' },
  executor: { label: '执行者', color: 'bg-green-500', description: '执行具体任务' },
  specialist: { label: '专家', color: 'bg-emerald-500', description: '提供专业服务' },
  validator: { label: '验证者', color: 'bg-orange-500', description: '检查结果正确性' },
  critic: { label: '批评者', color: 'bg-red-500', description: '提供改进建议' },
  synthesizer: { label: '综合者', color: 'bg-purple-500', description: '整合多个结果' },
};

const topologyConfig: Record<TeamTopology, { label: string; description: string }> = {
  hierarchical: { label: '层级式', description: 'Manager-Worker结构，适合结构化任务' },
  'peer-to-peer': { label: '对等式', description: '代理直接协作，适合探索性任务' },
  blackboard: { label: '黑板式', description: '共享工作空间，适合复杂问题求解' },
  pipeline: { label: '管道式', description: '顺序处理，适合数据处理流程' },
};

export function ClawTeamView() {
  const [activeTab, setActiveTab] = useState('teams');
  const [showCreateAgent, setShowCreateAgent] = useState(false);
  const [showCreateTeam, setShowCreateTeam] = useState(false);
  const [showExecuteTask, setShowExecuteTask] = useState(false);
  const [selectedTeamId, setSelectedTeamId] = useState<string | null>(null);
  
  const [newAgent, setNewAgent] = useState<Partial<Agent>>({
    role: 'executor',
    model: 'gpt-4',
    temperature: 0.7,
    maxTokens: 2000,
    tools: [],
  });
  const [newTeam, setNewTeam] = useState<Partial<AgentTeam>>({
    topology: 'hierarchical',
    agents: [],
  });
  const [taskDescription, setTaskDescription] = useState('');

  const agents = useApiStore((state) => state.clawteam.agents);
  const teams = useApiStore((state) => state.clawteam.teams);
  const tasks = useApiStore((state) => state.clawteam.tasks);
  const isExecuting = useApiStore((state) => state.clawteam.isExecuting);
  const createAgent = useApiStore((state) => state.clawteam.createAgent);
  const createTeam = useApiStore((state) => state.clawteam.createTeam);
  const executeTask = useApiStore((state) => state.clawteam.executeTask);
  const deleteAgent = useApiStore((state) => state.clawteam.deleteAgent);
  const deleteTeam = useApiStore((state) => state.clawteam.deleteTeam);
  const fetchAgents = useApiStore((state) => state.clawteam.fetchAgents);
  const fetchTeams = useApiStore((state) => state.clawteam.fetchTeams);
  const fetchTasks = useApiStore((state) => state.clawteam.fetchTasks);

  // 加载数据
  useEffect(() => {
    fetchAgents();
    fetchTeams();
    fetchTasks();
  }, [fetchAgents, fetchTeams, fetchTasks]);

  const handleCreateAgent = async () => {
    if (!newAgent.name) return;
    
    await createAgent({
      name: newAgent.name,
      role: newAgent.role as AgentRole,
      description: newAgent.description || '',
      capabilities: newAgent.capabilities || [],
      systemPrompt: newAgent.systemPrompt || '',
      model: newAgent.model || 'gpt-4',
      temperature: newAgent.temperature || 0.7,
      maxTokens: newAgent.maxTokens || 2000,
      tools: newAgent.tools || [],
    });
    
    setShowCreateAgent(false);
    setNewAgent({
      role: 'executor',
      model: 'gpt-4',
      temperature: 0.7,
      maxTokens: 2000,
      tools: [],
    });
  };

  const handleCreateTeam = async () => {
    if (!newTeam.name) return;
    
    await createTeam({
      name: newTeam.name,
      description: newTeam.description || '',
      topology: newTeam.topology as TeamTopology,
      agents: newTeam.agents || [],
    });
    
    setShowCreateTeam(false);
    setNewTeam({
      topology: 'hierarchical',
      agents: [],
    });
  };

  const handleExecuteTask = async () => {
    if (!selectedTeamId || !taskDescription) return;
    
    await executeTask(selectedTeamId, taskDescription);
    setShowExecuteTask(false);
    setTaskDescription('');
  };

  const getStatusIcon = (status: Task['status']) => {
    switch (status) {
      case 'completed':
        return <CheckCircle className="h-4 w-4 text-green-500" />;
      case 'failed':
        return <XCircle className="h-4 w-4 text-red-500" />;
      case 'running':
        return <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-primary" />;
      default:
        return <Clock className="h-4 w-4 text-muted-foreground" />;
    }
  };

  return (
    <div className="flex h-full">
      <div className="flex-1 flex flex-col">
        <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col">
          <div className="flex items-center justify-between px-4 py-2 border-b bg-card/50">
            <TabsList>
              <TabsTrigger value="teams" className="gap-1">
                <Users className="h-4 w-4" />
                代理团队
              </TabsTrigger>
              <TabsTrigger value="agents" className="gap-1">
                <Bot className="h-4 w-4" />
                代理管理
              </TabsTrigger>
              <TabsTrigger value="tasks" className="gap-1">
                <Zap className="h-4 w-4" />
                任务历史
              </TabsTrigger>
            </TabsList>
            
            <div className="flex items-center gap-2">
              {activeTab === 'teams' && (
                <Dialog open={showCreateTeam} onOpenChange={setShowCreateTeam}>
                  <DialogTrigger asChild>
                    <Button size="sm" className="gap-1">
                      <Plus className="h-4 w-4" />
                      创建团队
                    </Button>
                  </DialogTrigger>
                  <DialogContent className="max-w-lg">
                    <DialogHeader>
                      <DialogTitle>创建代理团队</DialogTitle>
                      <DialogDescription>
                        配置一个自定义的AI代理团队来处理特定任务
                      </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4 py-4">
                      <div className="space-y-2">
                        <label className="text-sm font-medium">团队名称</label>
                        <Input
                          value={newTeam.name || ''}
                          onChange={(e) => setNewTeam({ ...newTeam, name: e.target.value })}
                          placeholder="例如：代码审查团队"
                        />
                      </div>
                      <div className="space-y-2">
                        <label className="text-sm font-medium">描述</label>
                        <Textarea
                          value={newTeam.description || ''}
                          onChange={(e) => setNewTeam({ ...newTeam, description: e.target.value })}
                          placeholder="描述团队的职责和用途..."
                        />
                      </div>
                      <div className="space-y-2">
                        <label className="text-sm font-medium">团队拓扑</label>
                        <div className="grid grid-cols-2 gap-2">
                          {(Object.keys(topologyConfig) as TeamTopology[]).map((topology) => (
                            <button
                              key={topology}
                              onClick={() => setNewTeam({ ...newTeam, topology })}
                              className={cn(
                                "p-3 rounded-lg border text-left transition-colors",
                                newTeam.topology === topology
                                  ? "border-primary bg-primary/5"
                                  : "hover:bg-accent"
                              )}
                            >
                              <div className="font-medium text-sm">{topologyConfig[topology].label}</div>
                              <div className="text-xs text-muted-foreground mt-1">
                                {topologyConfig[topology].description}
                              </div>
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>
                    <DialogFooter>
                      <Button variant="outline" onClick={() => setShowCreateTeam(false)}>
                        取消
                      </Button>
                      <Button onClick={handleCreateTeam}>创建</Button>
                    </DialogFooter>
                  </DialogContent>
                </Dialog>
              )}
              
              {activeTab === 'agents' && (
                <Dialog open={showCreateAgent} onOpenChange={setShowCreateAgent}>
                  <DialogTrigger asChild>
                    <Button size="sm" className="gap-1">
                      <Plus className="h-4 w-4" />
                      创建代理
                    </Button>
                  </DialogTrigger>
                  <DialogContent className="max-w-lg">
                    <DialogHeader>
                      <DialogTitle>创建AI代理</DialogTitle>
                      <DialogDescription>
                        配置一个具有特定角色和能力的AI代理
                      </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4 py-4">
                      <div className="space-y-2">
                        <label className="text-sm font-medium">代理名称</label>
                        <Input
                          value={newAgent.name || ''}
                          onChange={(e) => setNewAgent({ ...newAgent, name: e.target.value })}
                          placeholder="例如：代码专家"
                        />
                      </div>
                      <div className="space-y-2">
                        <label className="text-sm font-medium">角色</label>
                        <div className="grid grid-cols-4 gap-2">
                          {(Object.keys(roleConfig) as AgentRole[]).map((role) => (
                            <button
                              key={role}
                              onClick={() => setNewAgent({ ...newAgent, role })}
                              className={cn(
                                "p-2 rounded-lg border text-center transition-colors",
                                newAgent.role === role
                                  ? "border-primary bg-primary/5"
                                  : "hover:bg-accent"
                              )}
                            >
                              <div className={cn(
                                "w-3 h-3 rounded-full mx-auto mb-1",
                                roleConfig[role].color
                              )} />
                              <div className="text-xs font-medium">{roleConfig[role].label}</div>
                            </button>
                          ))}
                        </div>
                      </div>
                      <div className="space-y-2">
                        <label className="text-sm font-medium">描述</label>
                        <Textarea
                          value={newAgent.description || ''}
                          onChange={(e) => setNewAgent({ ...newAgent, description: e.target.value })}
                          placeholder="描述代理的职责和能力..."
                        />
                      </div>
                      <div className="space-y-2">
                        <label className="text-sm font-medium">系统提示词</label>
                        <Textarea
                          value={newAgent.systemPrompt || ''}
                          onChange={(e) => setNewAgent({ ...newAgent, systemPrompt: e.target.value })}
                          placeholder="定义代理的行为和响应方式..."
                        />
                      </div>
                    </div>
                    <DialogFooter>
                      <Button variant="outline" onClick={() => setShowCreateAgent(false)}>
                        取消
                      </Button>
                      <Button onClick={handleCreateAgent}>创建</Button>
                    </DialogFooter>
                  </DialogContent>
                </Dialog>
              )}
            </div>
          </div>

          <TabsContent value="teams" className="flex-1 m-0 p-4">
            <div className="grid grid-cols-3 gap-4">
              {teams.length === 0 ? (
                <div className="col-span-3 text-center py-12 text-muted-foreground">
                  <Users className="h-12 w-12 mx-auto mb-4 opacity-50" />
                  <p>暂无代理团队</p>
                  <p className="text-sm mt-1">创建团队来组织多个代理协作完成任务</p>
                </div>
              ) : (
                teams.map((team) => (
                  <Card key={team.id}>
                    <CardHeader className="pb-3">
                      <div className="flex items-start justify-between">
                        <div>
                          <CardTitle className="text-lg">{team.name}</CardTitle>
                          <CardDescription className="mt-1">
                            {team.description || '暂无描述'}
                          </CardDescription>
                        </div>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-8 w-8">
                              <MoreVertical className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem>
                              <Edit className="h-4 w-4 mr-2" />
                              编辑
                            </DropdownMenuItem>
                            <DropdownMenuItem 
                              className="text-destructive"
                              onClick={() => deleteTeam(team.id)}
                            >
                              <Trash2 className="h-4 w-4 mr-2" />
                              删除
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-3">
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-muted-foreground">拓扑结构</span>
                          <Badge variant="outline">
                            {topologyConfig[team.topology].label}
                          </Badge>
                        </div>
                        <div className="flex items-center justify-between text-sm">
                          <span className="text-muted-foreground">代理数量</span>
                          <span>{team.agents.length}</span>
                        </div>
                        <div className="pt-2">
                          <Button 
                            className="w-full gap-1"
                            onClick={() => {
                              setSelectedTeamId(team.id);
                              setShowExecuteTask(true);
                            }}
                          >
                            <Play className="h-4 w-4" />
                            执行任务
                          </Button>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ))
              )}
            </div>
          </TabsContent>

          <TabsContent value="agents" className="flex-1 m-0 p-4">
            <div className="grid grid-cols-4 gap-4">
              {agents.length === 0 ? (
                <div className="col-span-4 text-center py-12 text-muted-foreground">
                  <Bot className="h-12 w-12 mx-auto mb-4 opacity-50" />
                  <p>暂无AI代理</p>
                  <p className="text-sm mt-1">创建代理来执行特定任务</p>
                </div>
              ) : (
                agents.map((agent) => (
                  <Card key={agent.id}>
                    <CardHeader className="pb-3">
                      <div className="flex items-start justify-between">
                        <div className="flex items-center gap-2">
                          <div className={cn(
                            "w-8 h-8 rounded-full flex items-center justify-center",
                            roleConfig[agent.role].color
                          )}>
                            <Bot className="h-4 w-4 text-white" />
                          </div>
                          <div>
                            <CardTitle className="text-base">{agent.name}</CardTitle>
                            <Badge variant="secondary" className="text-[10px] mt-0.5">
                              {roleConfig[agent.role].label}
                            </Badge>
                          </div>
                        </div>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-7 w-7">
                              <MoreVertical className="h-3 w-3" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem>
                              <Edit className="h-4 w-4 mr-2" />
                              编辑
                            </DropdownMenuItem>
                            <DropdownMenuItem 
                              className="text-destructive"
                              onClick={() => deleteAgent(agent.id)}
                            >
                              <Trash2 className="h-4 w-4 mr-2" />
                              删除
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    </CardHeader>
                    <CardContent>
                      <p className="text-sm text-muted-foreground line-clamp-2">
                        {agent.description || '暂无描述'}
                      </p>
                      <div className="flex items-center gap-2 mt-3">
                        <Badge variant="outline" className="text-xs">
                          {agent.model}
                        </Badge>
                        <span className="text-xs text-muted-foreground">
                          T={agent.temperature}
                        </span>
                      </div>
                    </CardContent>
                  </Card>
                ))
              )}
            </div>
          </TabsContent>

          <TabsContent value="tasks" className="flex-1 m-0">
            <ScrollArea className="h-[calc(100vh-10rem)]">
              <div className="p-4 space-y-3">
                {tasks.length === 0 ? (
                  <div className="text-center py-12 text-muted-foreground">
                    <Zap className="h-12 w-12 mx-auto mb-4 opacity-50" />
                    <p>暂无任务记录</p>
                    <p className="text-sm mt-1">从团队页面执行任务</p>
                  </div>
                ) : (
                  tasks.map((task) => (
                    <Card key={task.id}>
                      <CardContent className="p-4">
                        <div className="flex items-start gap-3">
                          {getStatusIcon(task.status)}
                          <div className="flex-1">
                            <div className="flex items-center justify-between">
                              <h4 className="font-medium">{task.description.slice(0, 50)}...</h4>
                              <Badge variant={
                                task.status === 'completed' ? 'default' :
                                task.status === 'failed' ? 'destructive' :
                                task.status === 'running' ? 'secondary' :
                                'outline'
                              }>
                                {task.status === 'completed' ? '已完成' :
                                 task.status === 'failed' ? '失败' :
                                 task.status === 'running' ? '执行中' :
                                 '待执行'}
                              </Badge>
                            </div>
                            <p className="text-sm text-muted-foreground mt-1">
                              团队: {teams.find(t => t.id === task.teamId)?.name || '未知'}
                            </p>
                            <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
                              <span>优先级: {task.priority}</span>
                              <span>子任务: {task.subtasks.length}</span>
                              {task.startedAt && (
                                <span>开始: {new Date(task.startedAt).toLocaleString()}</span>
                              )}
                            </div>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  ))
                )}
              </div>
            </ScrollArea>
          </TabsContent>
        </Tabs>
      </div>

      <Dialog open={showExecuteTask} onOpenChange={setShowExecuteTask}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>执行任务</DialogTitle>
            <DialogDescription>
              向代理团队分配任务
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">任务描述</label>
              <Textarea
                value={taskDescription}
                onChange={(e) => setTaskDescription(e.target.value)}
                placeholder="描述需要代理团队完成的任务..."
                rows={5}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowExecuteTask(false)}>
              取消
            </Button>
            <Button 
              onClick={handleExecuteTask}
              disabled={!taskDescription || isExecuting}
              className="gap-1"
            >
              {isExecuting && <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />}
              {isExecuting ? '执行中...' : '开始执行'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
   