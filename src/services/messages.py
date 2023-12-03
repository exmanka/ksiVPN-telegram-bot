from inspect import cleandoc

messages_dict = \
{
    'hello_message':
    {
        'text': 
        'Тут должно быть приветственное сообщение, восхваляющее данный проект и рекомендующее подключить ksiVPN всем своим друзьям, родственниками, домашним животным и далее по списку. Но я его пока не придумал.\n\n\u2728\u2728\u2728 Так что ёпта привет, это тест! \u2728\u2728\u2728',
        
        'img_id':
        'AgACAgIAAxkBAAIBZWT4pf2JcOWwWqzq6BrDBplE_LefAALD0TEba5XBSwtXi502wnAvAQADAgADcwADMAQ'
    },

    'project_info':
    {
        'text':
        'Безлимитный, быстрый и полностью безопасный сервис, позволяющий устанавливать VPN-соединение в различных странах мира через собственные VPS за 200₽ в месяц.',

        'img_id':
        'AgACAgIAAxkBAAIBt2T4tvKfh4vtyw9E0esmv5ez8oipAAJH0jEba5XBS205NYeWh2RdAQADAgADcwADMAQ'
    },

    'project_rules':
    {
        'text':
        cleandoc(
        '''
        <b>При работе с сервисом обязательно:</b>

        1. Запрещается делиться конфигурациями (QR-кодами для смартфонов или файлами <code>*.conf</code> для ПК) с другими людьми. Одна конфигурация может быть использована только для одного Вашего устройства. При этом для своего пользования Вы можете запросить неограниченное количество дополнительных конфигураций. 

        2. Запрещается загружать файлы через торрент-клиенты. Однако сами файлы расширения <code>*.torrent</code> скачивать можно.
        <i>Пример: Вы хотите скачать фильм, однако сайт, на котором размещены файлы, недоступен из России. Вы включаете VPN, заходите на сайт и загружаете файл filmexample.torrent. Далее Вы отключаете VPN и приступаете к загрузке самого фильма в Вашем торрент-клиенте.</i>


        <b>При работе с сервисом рекомендуется:</b>

        1. Не использовать VPN в моментах, когда он Вам не нужен. Благодаря этому, Вы не будете испытывать проблем с Вашими приложениями.'
        ''')
    },

    'ref_program':
    {
        'text':
        cleandoc(
        '''
        <b>Ваааау! У нас появилась реферальная программа!</b>

        Описание_реферальной_программы
        '''
        )
    },

    'ref_program_invites':
    {
        'text':
        (
            cleandoc(
            '''
            Дарова, отец. Кидаю тебе инвайт в очень крутой VPN-проект (переходи в тг бота https://t.me/ksiVPN_bot)!
            При регистрации пошелести там, введи мой реферальный промокод <refcode>. Получишь месяц использования бесплатно!
            '''
            ),
            cleandoc(
            '''
            Ээээ, брат СубханаЛлах. VPN-ом пользуешься? В любом случае переходи в тг бота https://t.me/ksiVPN_bot и регистрируйся!
            В начале введи мой реферальный промокод <refcode>. Бесплатно будешь пользоваться VPN-ом целый месяц!
            '''
            ),
            cleandoc(
            '''
            Ребята, вы издеваетесь? Я понимаю, что вам просто хочется заходить в инстаграм и наслаждаться жизнью. Но почему вы используете такие ужасные VPN-сервисы?
            Набираю команду ребят, будем делать кэш на зарубежных сервисах: https://t.me/ksiVPN_bot.

            При регистрации вводи мой реферальный промокод <refcode> и получишь месяц использования бесплатно!
            '''
            ),
            cleandoc(
            '''
            Короче, Меченый, я тебя спас и в благородство играть не буду: зарегистрируешься в сервисе https://t.me/ksiVPN_bot – и мы в расчете.
            Заодно посмотрим, как быстро у тебя башка после использования бесплатных VPN-ов прояснится. А по поводу реферальных промокодов постараюсь разузнать.
            Хрен его знает, на кой ляд тебе этот месяц бесплатной подписки сдался, но я в чужие дела не лезу, хочешь использовать мой реферальной промокод <refcode>, значит есть за что…
            '''
            ),
            cleandoc(
            '''
            Мужчину спрашивают:
            - Что вы любите?
            - Инстаграмчик люблю! Инстаграмчик люблю пиз..ец! Сидел бы в инсте бл..ть 24 часа в сутки, просто все рилсы мира посмотрел бы, рилсы люблю аж рвёт, не могу жить без рилсов, инстаграмчик люблю пиз..ец!
            - Хм, ясно. А что ещё любите?
            - ChatGPT люблю! ChatGPT люблю пиз..ец! Др..чил бы его сутками, д..очил бы, д..очил бы и д..очил бы, хоть бы в штат OpenAI залез, только чтоб голова торчала!
            - Ээ.. а голова зачем?
            - Рилсы смотреть люблю пиз..ец!

            Анекдот предоставлен сервисом https://t.me/ksiVPN_bot.
            Вводи мой реферальный промокод <refcode> и получай месяц использования бесплатно при регистрации!
            '''
            )
        )
    }

}