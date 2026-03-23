import { useState } from 'react';
import { 
  X, Moon, Sun, Monitor, Palette, 
  Key, Plug, Database, Save
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Switch } from '@/components/ui/switch';
import { useTheme } from '@/components/Theme/ThemeProvider';
import { cn } from '@/lib/utils';

interface SettingsPanelProps {
  isOpen: boolean;
  onClose: () => void;
}

const colorOptions = [
  { id: 'default', name: '默认', color: 'bg-gray-900', darkColor: 'bg-gray-100' },
  { id: 'blue', name: '蓝色', color: 'bg-blue-500', darkColor: 'bg-blue-400' },
  { id: 'purple', name: '紫色', color: 'bg-purple-500', darkColor: 'bg-purple-400' },
  { id: 'green', name: '绿色', color: 'bg-green-500', darkColor: 'bg-green-400' },
  { id: 'orange', name: '橙色', color: 'bg-orange-500', darkColor: 'bg-orange-400' },
  { id: 'pink', name: '粉色', color: 'bg-pink-500', darkColor: 'bg-pink-400' },
] as const;

export function SettingsPanel({ isOpen, onClose }: SettingsPanelProps) {
  const { theme, colorTheme, setTheme, setColorTheme } = useTheme();
  
  // API配置状态
  const [apiConfig, setApiConfig] = useState({
    openaiApiKey: localStorage.getItem('openai-api-key') || '',
    openaiBaseUrl: localStorage.getItem('openai-base-url') || 'https://api.openai.com/v1',
    azureApiKey: localStorage.getItem('azure-api-key') || '',
    azureEndpoint: localStorage.getItem('azure-endpoint') || '',
    defaultModel: localStorage.getItem('default-model') || 'gpt-4',
  });

  const handleSaveApiConfig = () => {
    localStorage.setItem('openai-api-key', apiConfig.openaiApiKey);
    localStorage.setItem('openai-base-url', apiConfig.openaiBaseUrl);
    localStorage.setItem('azure-api-key', apiConfig.azureApiKey);
    localStorage.setItem('azure-endpoint', apiConfig.azureEndpoint);
    localStorage.setItem('default-model', apiConfig.defaultModel);
    
    // 触发保存成功提示
    const event = new CustomEvent('toast', { 
      detail: { message: 'API配置已保存', type: 'success' } 
    });
    window.dispatchEvent(event);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-background rounded-lg shadow-lg w-full max-w-2xl max-h-[80vh] flex flex-col">
        {/* 头部 */}
        <div className="flex items-center justify-between p-4 border-b">
          <h2 className="text-lg font-semibold">设置</h2>
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        {/* 内容 */}
        <Tabs defaultValue="appearance" className="flex-1 overflow-hidden">
          <div className="flex h-full">
            {/* 左侧标签 */}
            <TabsList className="flex-col h-full w-40 bg-muted/50 rounded-none border-r p-2">
              <TabsTrigger value="appearance" className="w-full justify-start gap-2">
                <Palette className="h-4 w-4" />
                外观
              </TabsTrigger>
              <TabsTrigger value="api" className="w-full justify-start gap-2">
                <Key className="h-4 w-4" />
                API配置
              </TabsTrigger>
              <TabsTrigger value="plugins" className="w-full justify-start gap-2">
                <Plug className="h-4 w-4" />
                插件
              </TabsTrigger>
              <TabsTrigger value="data" className="w-full justify-start gap-2">
                <Database className="h-4 w-4" />
                数据
              </TabsTrigger>
            </TabsList>

            {/* 右侧内容 */}
            <div className="flex-1 overflow-auto p-4">
              {/* 外观设置 */}
              <TabsContent value="appearance" className="mt-0 space-y-6">
                <div>
                  <h3 className="text-sm font-medium mb-3">主题模式</h3>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setTheme('light')}
                      className={cn(
                        "flex flex-col items-center gap-2 p-3 rounded-lg border transition-all",
                        theme === 'light' 
                          ? 'border-primary bg-primary/10' 
                          : 'border-border hover:bg-accent'
                      )}
                    >
                      <Sun className="h-5 w-5" />
                      <span className="text-xs">浅色</span>
                    </button>
                    <button
                      onClick={() => setTheme('dark')}
                      className={cn(
                        "flex flex-col items-center gap-2 p-3 rounded-lg border transition-all",
                        theme === 'dark' 
                          ? 'border-primary bg-primary/10' 
                          : 'border-border hover:bg-accent'
                      )}
                    >
                      <Moon className="h-5 w-5" />
                      <span className="text-xs">深色</span>
                    </button>
                    <button
                      onClick={() => setTheme('system')}
                      className={cn(
                        "flex flex-col items-center gap-2 p-3 rounded-lg border transition-all",
                        theme === 'system' 
                          ? 'border-primary bg-primary/10' 
                          : 'border-border hover:bg-accent'
                      )}
                    >
                      <Monitor className="h-5 w-5" />
                      <span className="text-xs">跟随系统</span>
                    </button>
                  </div>
                </div>

                <div>
                  <h3 className="text-sm font-medium mb-3">主题颜色</h3>
                  <div className="grid grid-cols-3 gap-2">
                    {colorOptions.map((option) => (
                      <button
                        key={option.id}
                        onClick={() => setColorTheme(option.id as any)}
                        className={cn(
                          "flex items-center gap-2 p-2 rounded-lg border transition-all",
                          colorTheme === option.id 
                            ? 'border-primary bg-primary/10' 
                            : 'border-border hover:bg-accent'
                        )}
                      >
                        <div className={cn(
                          "w-4 h-4 rounded-full",
                          theme === 'dark' ? option.darkColor : option.color
                        )} />
                        <span className="text-sm">{option.name}</span>
                      </button>
                    ))}
                  </div>
                </div>
              </TabsContent>

              {/* API配置 */}
              <TabsContent value="api" className="mt-0 space-y-6">
                <div>
                  <h3 className="text-sm font-medium mb-3">OpenAI 配置</h3>
                  <div className="space-y-3">
                    <div>
                      <Label htmlFor="openai-key">API Key</Label>
                      <Input
                        id="openai-key"
                        type="password"
                        value={apiConfig.openaiApiKey}
                        onChange={(e) => setApiConfig({ ...apiConfig, openaiApiKey: e.target.value })}
                        placeholder="sk-..."
                      />
                    </div>
                    <div>
                      <Label htmlFor="openai-url">Base URL</Label>
                      <Input
                        id="openai-url"
                        value={apiConfig.openaiBaseUrl}
                        onChange={(e) => setApiConfig({ ...apiConfig, openaiBaseUrl: e.target.value })}
                        placeholder="https://api.openai.com/v1"
                      />
                    </div>
                  </div>
                </div>

                <div>
                  <h3 className="text-sm font-medium mb-3">Azure OpenAI 配置</h3>
                  <div className="space-y-3">
                    <div>
                      <Label htmlFor="azure-key">API Key</Label>
                      <Input
                        id="azure-key"
                        type="password"
                        value={apiConfig.azureApiKey}
                        onChange={(e) => setApiConfig({ ...apiConfig, azureApiKey: e.target.value })}
                        placeholder="..."
                      />
                    </div>
                    <div>
                      <Label htmlFor="azure-endpoint">Endpoint</Label>
                      <Input
                        id="azure-endpoint"
                        value={apiConfig.azureEndpoint}
                        onChange={(e) => setApiConfig({ ...apiConfig, azureEndpoint: e.target.value })}
                        placeholder="https://...openai.azure.com/"
                      />
                    </div>
                  </div>
                </div>

                <div>
                  <h3 className="text-sm font-medium mb-3">默认模型</h3>
                  <Input
                    value={apiConfig.defaultModel}
                    onChange={(e) => setApiConfig({ ...apiConfig, defaultModel: e.target.value })}
                    placeholder="gpt-4"
                  />
                </div>

                <Button onClick={handleSaveApiConfig} className="w-full gap-2">
                  <Save className="h-4 w-4" />
                  保存配置
                </Button>
              </TabsContent>

              {/* 插件设置 */}
              <TabsContent value="plugins" className="mt-0">
                <PluginManager />
              </TabsContent>

              {/* 数据设置 */}
              <TabsContent value="data" className="mt-0 space-y-4">
                <div className="p-4 border rounded-lg">
                  <h3 className="text-sm font-medium mb-2">数据导出</h3>
                  <p className="text-xs text-muted-foreground mb-3">
                    导出所有笔记、记忆和配置为JSON文件
                  </p>
                  <Button variant="outline" size="sm">
                    导出数据
                  </Button>
                </div>
                <div className="p-4 border rounded-lg">
                  <h3 className="text-sm font-medium mb-2">数据导入</h3>
                  <p className="text-xs text-muted-foreground mb-3">
                    从JSON文件导入数据
                  </p>
                  <Button variant="outline" size="sm">
                    导入数据
                  </Button>
                </div>
                <div className="p-4 border rounded-lg border-destructive/50">
                  <h3 className="text-sm font-medium mb-2 text-destructive">危险区域</h3>
                  <p className="text-xs text-muted-foreground mb-3">
                    清除所有本地数据，此操作不可恢复
                  </p>
                  <Button variant="destructive" size="sm">
                    清除所有数据
                  </Button>
                </div>
              </TabsContent>
            </div>
          </div>
        </Tabs>
      </div>
    </div>
  );
}

// 插件管理器组件
function PluginManager() {
  const [plugins, setPlugins] = useState<Array<{
    id: string;
    name: string;
    version: string;
    description: string;
    author: string;
    isActive: boolean;
    isBuiltIn?: boolean;
  }>>(() => {
    // 从localStorage加载插件
    const saved = localStorage.getItem('claw-plugins');
    if (saved) {
      return JSON.parse(saved);
    }
    // 默认内置插件
    return [
      {
        id: 'knowledge-graph',
        name: '知识图谱可视化',
        version: '1.0.0',
        description: '以图形方式展示笔记之间的关联关系',
        author: 'Claw Team',
        isActive: true,
        isBuiltIn: true,
      },
      {
        id: 'markdown-tools',
        name: 'Markdown工具集',
        version: '1.0.0',
        description: '增强的Markdown编辑功能',
        author: 'Claw Team',
        isActive: true,
        isBuiltIn: true,
      },
      {
        id: 'memory-search',
        name: '记忆搜索增强',
        version: '1.0.0',
        description: '基于向量的语义记忆搜索',
        author: 'Claw Team',
        isActive: true,
        isBuiltIn: true,
      },
    ];
  });

  const [newPluginUrl, setNewPluginUrl] = useState('');
  const [isInstalling, setIsInstalling] = useState(false);

  const togglePlugin = (id: string) => {
    const updated = plugins.map(p => 
      p.id === id ? { ...p, isActive: !p.isActive } : p
    );
    setPlugins(updated);
    localStorage.setItem('claw-plugins', JSON.stringify(updated));
  };

  const installPlugin = async () => {
    if (!newPluginUrl) return;
    
    setIsInstalling(true);
    try {
      // 模拟从URL安装插件
      await new Promise(resolve => setTimeout(resolve, 1500));
      
      const newPlugin = {
        id: `plugin-${Date.now()}`,
        name: '自定义插件',
        version: '1.0.0',
        description: '从外部安装的插件',
        author: 'Unknown',
        isActive: true,
        isBuiltIn: false,
      };
      
      const updated = [...plugins, newPlugin];
      setPlugins(updated);
      localStorage.setItem('claw-plugins', JSON.stringify(updated));
      setNewPluginUrl('');
      
      const event = new CustomEvent('toast', { 
        detail: { message: '插件安装成功', type: 'success' } 
      });
      window.dispatchEvent(event);
    } catch (error) {
      const event = new CustomEvent('toast', { 
        detail: { message: '插件安装失败', type: 'error' } 
      });
      window.dispatchEvent(event);
    } finally {
      setIsInstalling(false);
    }
  };

  const uninstallPlugin = (id: string) => {
    const updated = plugins.filter(p => p.id !== id);
    setPlugins(updated);
    localStorage.setItem('claw-plugins', JSON.stringify(updated));
  };

  return (
    <div className="space-y-4">
      {/* 安装新插件 */}
      <div className="p-4 border rounded-lg">
        <h3 className="text-sm font-medium mb-2">安装插件</h3>
        <div className="flex gap-2">
          <Input
            value={newPluginUrl}
            onChange={(e) => setNewPluginUrl(e.target.value)}
            placeholder="输入插件URL或本地路径..."
            className="flex-1"
          />
          <Button 
            onClick={installPlugin} 
            disabled={!newPluginUrl || isInstalling}
          >
            {isInstalling ? '安装中...' : '安装'}
          </Button>
        </div>
        <p className="text-xs text-muted-foreground mt-2">
          支持 .js, .json 格式的插件文件
        </p>
      </div>

      {/* 已安装插件列表 */}
      <div>
        <h3 className="text-sm font-medium mb-3">已安装插件 ({plugins.length})</h3>
        <div className="space-y-2">
          {plugins.map((plugin) => (
            <div 
              key={plugin.id} 
              className="flex items-center justify-between p-3 border rounded-lg"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-sm">{plugin.name}</span>
                  <span className="text-xs text-muted-foreground">v{plugin.version}</span>
                  {plugin.isBuiltIn && (
                    <span className="text-[10px] px-1.5 py-0.5 bg-secondary rounded">
                      内置
                    </span>
                  )}
                </div>
                <p className="text-xs text-muted-foreground truncate">
                  {plugin.description}
                </p>
                <p className="text-[10px] text-muted-foreground">
                  作者: {plugin.author}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Switch
                  checked={plugin.isActive}
                  onCheckedChange={() => togglePlugin(plugin.id)}
                />
                {!plugin.isBuiltIn && (
                  <Button 
                    variant="ghost" 
                    size="sm"
                    onClick={() => uninstallPlugin(plugin.id)}
                  >
                    卸载
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
