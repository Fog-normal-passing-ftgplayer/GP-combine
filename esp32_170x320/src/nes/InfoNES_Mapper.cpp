/*===================================================================*/
/*                                                                   */
/*  InfoNES_Mapper.cpp : InfoNES Mapper Function                     */
/*                                                                   */
/*  2000/05/16  InfoNES Project ( based on NesterJ and pNesX )       */
/*                                                                   */
/*===================================================================*/

/*-------------------------------------------------------------------*/
/*  Include files                                                    */
/*-------------------------------------------------------------------*/

#pragma GCC optimize("O2")   // 模拟器热点：默认 -Os 帧率不够
#include "InfoNES.h"
#include "InfoNES_System.h"
#include "InfoNES_Mapper.h"
#include "K6502.h"

/*-------------------------------------------------------------------*/
/*  Mapper resources                                                 */
/*-------------------------------------------------------------------*/

/* Disk System RAM */
BYTE *DRAM = 0;   // PSRAM（EspNesAllocBuffers 分配）

/*-------------------------------------------------------------------*/
/*  Table of Mapper initialize function                              */
/*-------------------------------------------------------------------*/

struct MapperTable_tag MapperTable[] =
{
  {   0, Map0_Init   },
  {   1, Map1_Init   },
  {   2, Map2_Init   },
  {   3, Map3_Init   },
  {   4, Map4_Init   },
  {   7, Map7_Init   },
  {  -1, NULL         }
};

/*-------------------------------------------------------------------*/
/*  body of Mapper functions                                         */
/*-------------------------------------------------------------------*/

#include "mapper/InfoNES_Mapper_000.h"
#include "mapper/InfoNES_Mapper_001.h"
#include "mapper/InfoNES_Mapper_002.h"
#include "mapper/InfoNES_Mapper_003.h"
#include "mapper/InfoNES_Mapper_004.h"
/* trimmed: #include "mapper/InfoNES_Mapper_005.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_006.h" */
#include "mapper/InfoNES_Mapper_007.h"
/* trimmed: #include "mapper/InfoNES_Mapper_008.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_009.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_010.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_011.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_013.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_015.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_016.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_017.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_018.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_019.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_021.h" */          
/* trimmed: #include "mapper/InfoNES_Mapper_022.h" */  
/* trimmed: #include "mapper/InfoNES_Mapper_023.h" */  
/* trimmed: #include "mapper/InfoNES_Mapper_024.h" */  
/* trimmed: #include "mapper/InfoNES_Mapper_025.h" */  
/* trimmed: #include "mapper/InfoNES_Mapper_026.h" */  
/* trimmed: #include "mapper/InfoNES_Mapper_032.h" */  
/* trimmed: #include "mapper/InfoNES_Mapper_033.h" */ 
/* trimmed: #include "mapper/InfoNES_Mapper_034.h" */ 
/* trimmed: #include "mapper/InfoNES_Mapper_040.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_041.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_042.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_043.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_044.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_045.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_046.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_047.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_048.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_049.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_050.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_051.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_057.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_058.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_060.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_061.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_062.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_064.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_065.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_066.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_067.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_068.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_069.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_070.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_071.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_072.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_073.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_074.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_075.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_076.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_077.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_078.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_079.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_080.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_082.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_083.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_085.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_086.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_087.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_088.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_089.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_090.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_091.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_092.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_093.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_094.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_095.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_096.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_097.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_099.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_100.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_101.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_105.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_107.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_108.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_109.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_110.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_112.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_113.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_114.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_115.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_116.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_117.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_118.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_119.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_122.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_133.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_134.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_135.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_140.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_151.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_160.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_180.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_181.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_182.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_183.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_185.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_187.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_188.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_189.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_191.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_193.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_194.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_200.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_201.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_202.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_222.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_225.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_226.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_227.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_228.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_229.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_230.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_231.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_232.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_233.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_234.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_235.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_236.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_240.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_241.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_242.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_243.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_244.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_245.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_246.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_248.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_249.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_251.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_252.h" */
/* trimmed: #include "mapper/InfoNES_Mapper_255.h" */

/* End of InfoNES_Mapper.cpp */
