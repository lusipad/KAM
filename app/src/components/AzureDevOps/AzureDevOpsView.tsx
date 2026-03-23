import { useState, useEffect } from 'react';
import { 
  GitBranch, Plus, RefreshCw, CheckCircle, 
  Search, ExternalLink, Code
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
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
import { useApiStore } from '@/store/apiStore';
import { cn } from '@/lib/utils';
import type { AzureDevOpsConfig } from '@/types';

export function AzureDevOpsView() {
  const [activeTab, setActiveTab] = useState('workitems');
  const [showAddConfig, setShowAddConfig] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  
  const [newConfig, setNewConfig] = useState<Partial<AzureDevOpsConfig>>({
    authType: 'pat',
  });

  const configs = useApiStore((state) => state.azureDevOps.configs);
  const currentConfigId = useApiStore((state) => state.azureDevOps.currentConfigId);
  const workItems = useApiStore((state) => state.azureDevOps.workItems);
  const repositories = useApiStore((state) => state.azureDevOps.repositories);
  const builds = useApiStore((state) => state.azureDevOps.builds);
  const isSyncing = useApiStore((state) => state.azureDevOps.isSyncing);
  const createConfig = useApiStore((state) => state.azureDevOps.createConfig);
  const setCurrentConfig = useApiStore((state) => state.azureDevOps.setCurrentConfig);
  const fetchConfigs = useApiStore((state) => state.azureDevOps.fetchConfigs);
  const fetchWorkItems = useApiStore((state) => state.azureDevOps.fetchWorkItems);
  const fetchRepositories = useApiStore((state) => state.azureDevOps.fetchRepositories);
  const fetchBuilds = useApiStore((state) => state.azureDevOps.fetchBuilds);

  // 加载配置
  useEffect(() => {
    fetchConfigs();
  }, [fetchConfigs]);

  const currentConfig = configs.find(c => c.id === currentConfigId);

  const handleAddConfig = async () => {
    if (!newConfig.name || !newConfig.serverUrl || !newConfig.project) return;
    
    await createConfig({
      name: newConfig.name,
      serverUrl: newConfig.serverUrl,
      collection: newConfig.collection || 'DefaultCollection',
      project: newConfig.project,
      authType: newConfig.authType as 'pat' | 'oauth' | 'ntlm',
      credentials: {
        pat: newConfig.credentials?.pat,
      },
    });
    
    setShowAddConfig(false);
    setNewConfig({ authType: 'pat' });
  };

  const getWorkItemStateColor = (state: string) => {
    switch (state?.toLowerCase()) {
      case 'new':
      case 'todo':
        return 'bg-gray-500';
      case 'active':
      case 'in progress':
        return 'bg-blue-500';
      case 'resolved':
      case 'done':
        return 'bg-green-500';
      case 'closed':
        return 'bg-purple-500';
      default:
        return 'bg-gray-400';
    }
  };

  const getBuildStatusColor = (status?: string, result?: string) => {
    if (result === 'succeeded') return 'text-green-500';
    if (result === 'failed') return 'text-red-500';
    if (result === 'partiallySucceeded') return 'text-yellow-500';
    if (status === 'inProgress') return 'text-blue-500';
    return 'text-gray-400';
  };

  return (
    <div className="flex h-full">
      <div className="w-72 flex-shrink-0 border-r bg-card/30 p-4">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold text-sm">Azure DevOps 配置</h2>
          <Dialog open={showAddConfig} onOpenChange={setShowAddConfig}>
            <DialogTrigger asChild>
              <Button variant="ghost" size="icon" className="h-7 w-7">
                <Plus className="h-4 w-4" />
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-lg">
              <DialogHeader>
                <DialogTitle>添加 Azure DevOps 配置</DialogTitle>
                <DialogDescription>
                  连接到 Azure DevOps Server 或 Azure DevOps Services
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-4 py-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium">配置名称</label>
                  <Input
                    value={newConfig.name || ''}
                    onChange={(e) => setNewConfig({ ...newConfig, name: e.target.value })}
                    placeholder="例如：公司项目"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">服务器 URL</label>
                  <Input
                    value={newConfig.serverUrl || ''}
                    onChange={(e) => setNewConfig({ ...newConfig, serverUrl: e.target.value })}
                    placeholder="https://dev.azure.com/organization 或 https://server:8080/tfs"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">项目集合</label>
                  <Input
                    value={newConfig.collection || ''}
                    onChange={(e) => setNewConfig({ ...newConfig, collection: e.target.value })}
                    placeholder="DefaultCollection"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">项目名称</label>
                  <Input
                    value={newConfig.project || ''}
                    onChange={(e) => setNewConfig({ ...newConfig, project: e.target.value })}
                    placeholder="MyProject"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">认证方式</label>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setNewConfig({ ...newConfig, authType: 'pat' })}
                      className={cn(
                        "flex-1 p-2 rounded-lg border text-center text-sm transition-colors",
                        newConfig.authType === 'pat'
                          ? "border-primary bg-primary/5"
                          : "hover:bg-accent"
                      )}
                    >
                      个人访问令牌 (PAT)
                    </button>
                    <button
                      onClick={() => setNewConfig({ ...newConfig, authType: 'oauth' })}
                      className={cn(
                        "flex-1 p-2 rounded-lg border text-center text-sm transition-colors",
                        newConfig.authType === 'oauth'
                          ? "border-primary bg-primary/5"
                          : "hover:bg-accent"
                      )}
                    >
                      OAuth
                    </button>
                  </div>
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">
                    {newConfig.authType === 'pat' ? '个人访问令牌' : 'Access Token'}
                  </label>
                  <Input
                    type="password"
                    value={newConfig.credentials?.pat || ''}
                    onChange={(e) => setNewConfig({ 
                      ...newConfig, 
                      credentials: { ...newConfig.credentials, pat: e.target.value }
                    })}
                    placeholder="输入您的访问令牌"
                  />
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setShowAddConfig(false)}>
                  取消
                </Button>
                <Button onClick={handleAddConfig}>添加配置</Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>

        <div className="space-y-2">
          {configs.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground text-sm">
              <GitBranch className="h-8 w-8 mx-auto mb-2 opacity-50" />
              <p>暂无配置</p>
              <p className="text-xs mt-1">点击 + 添加 Azure DevOps 连接</p>
            </div>
          ) : (
            configs.map((config) => (
              <button
                key={config.id}
                onClick={() => setCurrentConfig(config.id)}
                className={cn(
                  "w-full flex items-center gap-3 px-3 py-2 rounded-lg text-left transition-colors",
                  currentConfigId === config.id
                    ? "bg-primary/10 text-primary border border-primary/20"
                    : "hover:bg-accent text-muted-foreground"
                )}
              >
                <GitBranch className="h-4 w-4 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-sm truncate">{config.name}</div>
                  <div className="text-xs opacity-70 truncate">{config.project}</div>
                </div>
                {config.isActive && (
                  <div className="w-2 h-2 rounded-full bg-green-500 flex-shrink-0" />
                )}
              </button>
            ))
          )}
        </div>
      </div>

      <div className="flex-1 flex flex-col">
        {currentConfig ? (
          <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col">
            <div className="flex items-center justify-between px-4 py-2 border-b bg-card/50">
              <TabsList>
                <TabsTrigger value="workitems" className="gap-1">
                  <CheckCircle className="h-4 w-4" />
                  工作项
                </TabsTrigger>
                <TabsTrigger value="repositories" className="gap-1">
                  <Code className="h-4 w-4" />
                  代码仓库
                </TabsTrigger>
                <TabsTrigger value="builds" className="gap-1">
                  <GitBranch className="h-4 w-4" />
                  构建发布
                </TabsTrigger>
              </TabsList>
              
              <div className="flex items-center gap-2">
                <div className="relative">
                  <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="搜索..."
                    className="pl-8 h-8 w-48"
                  />
                </div>
                <Button 
                  variant="outline" 
                  size="sm" 
                  className="gap-1"
                  disabled={isSyncing}
                  onClick={() => {
                    if (activeTab === 'workitems') fetchWorkItems(currentConfig.id);
                    else if (activeTab === 'repositories') fetchRepositories(currentConfig.id);
                    else if (activeTab === 'builds') fetchBuilds(currentConfig.id);
                  }}
                >
                  {isSyncing ? (
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-primary" />
                  ) : (
                    <RefreshCw className="h-4 w-4" />
                  )}
                  同步
                </Button>
              </div>
            </div>

            <TabsContent value="workitems" className="flex-1 m-0">
              <ScrollArea className="h-[calc(100vh-10rem)]">
                <div className="p-4 space-y-3">
                  {workItems.length === 0 ? (
                    <div className="text-center py-12 text-muted-foreground">
                      <CheckCircle className="h-12 w-12 mx-auto mb-4 opacity-50" />
                      <p>暂无工作项</p>
                      <p className="text-sm mt-1">点击同步按钮获取工作项数据</p>
                    </div>
                  ) : (
                    workItems
                      .filter(wi => 
                        !searchQuery || 
                        wi.fields['System.Title']?.toLowerCase().includes(searchQuery.toLowerCase())
                      )
                      .map((workItem) => (
                      <Card key={workItem.id}>
                        <CardContent className="p-4">
                          <div className="flex items-start gap-3">
                            <div className={cn(
                              "w-3 h-3 rounded-full mt-1 flex-shrink-0",
                              getWorkItemStateColor(workItem.fields['System.State'])
                            )} />
                            <div className="flex-1">
                              <div className="flex items-center justify-between">
                                <h4 className="font-medium">
                                  {workItem.fields['System.Title']}
                                </h4>
                                <Badge variant="outline">#{workItem.id}</Badge>
                              </div>
                              <div className="flex items-center gap-4 mt-2 text-sm text-muted-foreground">
                                <span className="flex items-center gap-1">
                                  <CheckCircle className="h-3 w-3" />
                                  {workItem.fields['System.State']}
                                </span>
                                <span>{workItem.fields['System.WorkItemType']}</span>
                                {workItem.fields['System.AssignedTo'] && (
                                  <span>
                                    {workItem.fields['System.AssignedTo'].displayName}
                                  </span>
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

            <TabsContent value="repositories" className="flex-1 m-0">
              <ScrollArea className="h-[calc(100vh-10rem)]">
                <div className="p-4 space-y-3">
                  {repositories.length === 0 ? (
                    <div className="text-center py-12 text-muted-foreground">
                      <Code className="h-12 w-12 mx-auto mb-4 opacity-50" />
                      <p>暂无代码仓库</p>
                      <p className="text-sm mt-1">点击同步按钮获取仓库数据</p>
                    </div>
                  ) : (
                    repositories.map((repo) => (
                      <Card key={repo.id}>
                        <CardContent className="p-4">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                              <Code className="h-5 w-5 text-muted-foreground" />
                              <div>
                                <h4 className="font-medium">{repo.name}</h4>
                                <p className="text-sm text-muted-foreground">
                                  默认分支: {repo.defaultBranch}
                                </p>
                              </div>
                            </div>
                            <Button variant="ghost" size="icon" className="h-8 w-8">
                              <ExternalLink className="h-4 w-4" />
                            </Button>
                          </div>
                        </CardContent>
                      </Card>
                    ))
                  )}
                </div>
              </ScrollArea>
            </TabsContent>

            <TabsContent value="builds" className="flex-1 m-0">
              <ScrollArea className="h-[calc(100vh-10rem)]">
                <div className="p-4 space-y-3">
                  {builds.length === 0 ? (
                    <div className="text-center py-12 text-muted-foreground">
                      <GitBranch className="h-12 w-12 mx-auto mb-4 opacity-50" />
                      <p>暂无构建记录</p>
                      <p className="text-sm mt-1">点击同步按钮获取构建数据</p>
                    </div>
                  ) : (
                    builds.map((build) => (
                      <Card key={build.id}>
                        <CardContent className="p-4">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                              <GitBranch className={cn(
                                "h-5 w-5",
                                getBuildStatusColor(build.status, build.result)
                              )} />
                              <div>
                                <div className="flex items-center gap-2">
                                  <h4 className="font-medium">{build.definition.name}</h4>
                                  <Badge variant="outline">#{build.buildNumber}</Badge>
                                </div>
                                <p className="text-sm text-muted-foreground">
                                  请求者: {build.requester.displayName}
                                </p>
                              </div>
                            </div>
                            <div className="text-right text-sm text-muted-foreground">
                              <div>{build.status}</div>
                              {build.result && <div>{build.result}</div>}
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
        ) : (
          <div className="flex items-center justify-center h-full text-muted-foreground">
            <div className="text-center">
              <GitBranch className="h-16 w-16 mx-auto mb-4 opacity-50" />
              <p className="text-lg font-medium">选择或添加 Azure DevOps 配置</p>
              <p className="text-sm mt-2">从左侧选择一个配置或添加新配置</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
