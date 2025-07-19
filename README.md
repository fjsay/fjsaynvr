在监控存储的选择中，“云存储”曾因“即开即用”“无需本地硬件”的特点吸引了不少用户，但随着使用深入，其隐藏的成本痛点逐渐暴露：按摄像头数量、存储时长、清晰度阶梯收费，一个家庭3-4台摄像头，一年下来动辄数百元，长期使用成本远超NAS一次性投入。更重要的是，隐私数据存于云端始终存在泄露风险，而NAS作为本地存储中心，配合这款RTSP录像工具，恰好能打造一套“低成本、高安全、全自主”的监控存储方案。


## 一、文件准备与目录结构

### 1. 目录创建
在NAS中创建监控录像主目录及子目录，结构如下：
```
/vol3/1000/rtsp/          # 主目录
├─ conf/                  # 存放摄像头配置文件
├─ Video/                 # 存放录像文件（对应容器内的/Video）
└─ log/                   # 存放程序运行日志
```


### 2. 配置文件说明（**注意：txt文件不可包含注释内容**）

#### （1）摄像头配置文件（`conf/conf.txt`）
在`conf`文件夹下创建`conf.txt`（**必须为UTF-8格式，且不可包含任何注释行**），用于配置摄像头参数，格式严格遵循：  
`ID,RTSP地址,保留天数,录制时长(秒),保存格式,最小文件大小(KB)`  

示例内容（直接写入以下内容，无#注释）：
```
cam1,rtsp://admin:123456@192.168.1.100:554/stream,7,300,mp4,1024
cam2,rtsp://user:pass@192.168.1.101:554/h264,30,60,flv,0
```

参数说明：
- **ID**：自定义摄像头名称（如cam1、door、yard，不可包含逗号）
- **RTSP地址**：摄像头的RTSP流地址（需包含用户名和密码，格式参考下文）
- **保留天数**：录像文件保留天数（0表示永久保留，需为非负整数）
- **录制时长**：每段录像的时长（秒，需为正整数，建议30-300）
- **保存格式**：仅支持mp4、flv（小写，其他格式无效）
- **最小文件大小**：小于该值的文件会被自动删除（KB，0表示不删除，需为非负整数）


#### （2）日志配置文件（`conf/logconf.txt`）
在`conf`文件夹下可创建`logconf.txt`（**必须为UTF-8格式，且不可包含任何注释行**），内容仅为一个阿拉伯数字，代表日志保留天数。  

示例内容（直接写入以下内容，无#注释）：
```
7
```


### 3. 国内常见IP摄像头RTSP地址参考

| 品牌       | 主码流（高清）RTSP地址                          | 子码流（标清）RTSP地址                          |
|------------|-------------------------------------------------|-------------------------------------------------|
| 海康威视   | `rtsp://user:password@ip:554/h264/ch1/main/av_stream` | `rtsp://user:password@ip:554/mpeg4/ch1/sub/av_stream` |
| 大华       | `rtsp://username:password@ip:port/cam/realmonitor?channel=1&subtype=0` | -                                               |
| TP-Link/水星 | `rtsp://user:password@ip:554/stream1`           | `rtsp://user:password@ip:554/stream2`           |
| 三星       | `rtsp://user:password@ip:554/onvif/profile2/media.smp`（720P） | `rtsp://user:password@ip:554/onvif/profile3/media.smp` |
| LG         | `rtsp://user:password@ip:554/Master-0`          | `rtsp://user:password@ip:554/Slave-0`           |

> 注：将`user`/`password`替换为摄像头的用户名和密码，`ip`替换为摄像头的局域网IP。


## 二、Docker Compose配置

创建`docker-compose.yml`文件，内容如下：
```yaml
version: '3'

services:
  fjsaynvr:
    image: fjsay/fjsaynvr:v1.0
    container_name: fjsaynvr
    restart: always          # 容器异常时自动重启
    network_mode: host       # 使用主机网络，确保访问局域网摄像头
    volumes:
      - /你本地的地址/conf:/app/conf    # 映射摄像头配置目录（如/vol3/1000/rtsp/conf）
      - /你本地的地址/Video:/app/Video  # 映射录像存储目录（如/vol3/1000/rtsp/Video）
      - /你本地的地址/log:/app/log      # 映射日志目录（如/vol3/1000/rtsp/log）
```

> 替换`/你本地的地址`为实际的NAS目录路径（如`/vol3/1000/rtsp`）。


## 三、部署步骤

1. 将上述`docker-compose.yml`文件放入NAS的监控主目录（如`/vol3/1000/rtsp/`）
2. 通过NAS的终端工具（如群晖的“终端机”）进入该目录，执行启动命令：
   ```bash
   docker-compose up -d
   ```
3. 验证启动状态：
   ```bash
   docker ps | grep fjsaynvr  # 查看容器是否运行（状态为Up）
   docker logs -f fjsaynvr    # 查看实时日志，确认摄像头连接状态
   ```


## 四、注意事项

- 若`conf.txt`格式错误（如包含注释、逗号缺失、参数无效），工具会忽略错误行，仅加载正确配置
- 日志保留天数默认为7天，若`logconf.txt`格式错误（如非数字、包含文字），将自动使用默认值
- 确保NAS已安装Docker（可在NAS的“套件中心”搜索安装）
- 摄像头与NAS需在同一局域网，且RTSP端口（默认554）未被防火墙拦截

通过这套方案，你可以充分利用NAS的本地存储能力，摆脱云存储的持续收费和隐私风险，实现监控录像的自主管理。
