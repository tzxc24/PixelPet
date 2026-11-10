"""Export simulator bytes without assuming physical screen wiring or colour order."""
from fastapi import APIRouter,Response
from pydantic import BaseModel,Field,model_validator

router=APIRouter(prefix='/api/assets')


class Frame(BaseModel):
    width:int=Field(ge=1,le=240)
    height:int=Field(ge=1,le=240)
    rgba:list[int]=Field(max_length=230400)

    @model_validator(mode='after')
    def dimensions(self):
        if len(self.rgba)!=self.width*self.height*4 or any(v<0 or v>255 for v in self.rgba):
            raise ValueError('RGBA dimensions or channel values invalid')
        return self


@router.post('/rgb565')
async def rgb565(frame:Frame):
    data=bytearray()
    for i in range(0,len(frame.rgba),4):
        r,g,b,a=frame.rgba[i:i+4]
        r=(r*a+243*(255-a))//255;g=(g*a+243*(255-a))//255;b=(b*a+233*(255-a))//255
        value=((r>>3)<<11)|((g>>2)<<5)|(b>>3)
        data.extend((value&255,value>>8))
    return Response(bytes(data),media_type='application/octet-stream',headers={'Content-Disposition':'attachment; filename="pixelpet-rgb565-le.bin"','X-Pixel-Format':'RGB565_LE_RGB','X-Screen-Width':str(frame.width),'X-Screen-Height':str(frame.height),'X-Hardware-Status':'HW_PENDING'})
