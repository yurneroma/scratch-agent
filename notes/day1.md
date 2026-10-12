# while true 循环
  - 构造message 
  - agent.message.create() 送给背后的大模型
  - 获取response，  add to message， 如果有错误，同时把用户的input 也抛弃掉， 保证输入，输出是一对。 

# 这是最简单的一个agent loop