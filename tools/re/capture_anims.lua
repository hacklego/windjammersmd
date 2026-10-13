-- RE helper (MAME autoboot script): play a scripted Windjammers match and log, per frame,
-- the sprite columns that use character palettes (0x20-0x2B). Output: $OUT/anim_log.txt
-- Lines: frame n x y tile attr   (first tile of each sprite column)
local P=manager.machine.ioport.ports
local mem=manager.machine.devices[':maincpu'].spaces['program']
local vram={} for i=0,0xFFFF do vram[i]=0 end
local vaddr,vmod=0,0
function install()
  TAP=mem:install_write_tap(0x3C0000,0x3DFFFF,'vram',function(off,data,mask)
    local r=off&0xE
    if r==0 then vaddr=data
    elseif r==2 then vram[vaddr]=data; vaddr=(vaddr&0x8000)|((vaddr+vmod)&0x7FFF)
    elseif r==4 then vmod=data; if vmod>=0x8000 then vmod=vmod-0x10000 end end
  end)
end
install()
local J1=':edge:joy:JOY1'
local sched={
 {900,910,':AUDIO_COIN','Coin 1'},{1000,1010,':edge:joy:START','1 Player Start'},
 {1300,1310,J1,'P1 A'},{1500,1510,J1,'P1 A'},{1700,1710,J1,'P1 A'},{1900,1910,J1,'P1 A'},
}
-- character select cursor moves before confirming (env SELECT, e.g. "R", "DD", "DDR")
do local fr=1600
  for c in string.gmatch(os.getenv('SELECT') or '','.') do
    local m={R='P1 Right',L='P1 Left',U='P1 Up',D='P1 Down'}
    sched[#sched+1]={fr,fr+4,J1,m[c]}; fr=fr+20
  end
end
-- gameplay actions (from env ACTIONS="start end field;..." or defaults)
local acts=os.getenv('ACTIONS') or '2650 2700 P1 Right;2710 2760 P1 Up;2770 2820 P1 Down;2830 2880 P1 Left;2890 2892 P1 A;2950 2952 P1 B;3010 3040 P1 Right;3015 3017 P1 A;3100 3102 P1 A;3160 3162 P1 B'
for s,e,f in string.gmatch(acts,'(%d+) (%d+) ([^;]+)') do sched[#sched+1]={tonumber(s),tonumber(e),J1,f} end
local out=io.open(os.getenv('OUT')..'/anim_log'..(os.getenv('TAG') or '')..'.txt','w')
local f=0
local endf=tonumber(os.getenv('ENDF') or '3300')
emu.register_frame_done(function()
  f=f+1
  if TAP then TAP:remove() end
  install()
  for _,s in ipairs(sched) do
    local fl=P[s[3]].fields[s[4]]
    if f==s[1] then fl:set_value(1) elseif f==s[2] then fl:set_value(0) end
  end
  if f>=2600 then
    local held={}
    for _,sc in ipairs(sched) do if f>=sc[1] and f<sc[2] and sc[3]==J1 then held[#held+1]=sc[4]:gsub('P1 ','') end end
    out:write(string.format('I %d %s\n',f,table.concat(held,'+')))
    local px,py,ph=0,0,0
    for n=1,380 do
      local scb3=vram[0x8200+n]; local x,y,h
      if scb3&0x40~=0 then x=(px+16)&0x1FF; y=py; h=ph
      else x=vram[0x8400+n]>>7; y=(496-(scb3>>7))&0x1FF; h=scb3&0x3F end
      px,py,ph=x,y,h
      if h>0 then
        local at=vram[n*64+1]; local pl=at>>8
        if pl>=0x20 and pl<=0x2B then
          out:write(string.format('%d %d %d %d %04x %04x\n',f,n,x,y,vram[n*64],at))
        end
      end
    end
  end
  if f>=endf then out:close(); manager.machine:exit() end
end)
